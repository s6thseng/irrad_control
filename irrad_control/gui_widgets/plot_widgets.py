import logging
import pyqtgraph as pg
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
from collections import OrderedDict

# Matplotlib first 8 default colors
MPL_COLORS = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
              (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]

BOLD_FONT = QtGui.QFont()
BOLD_FONT.setBold(True)


class PlotWindow(QtWidgets.QMainWindow):
    """Window which only shows a PlotWidget as its central widget."""
        
    # PyQt signal which is emitted when the window closes
    closeWin = QtCore.pyqtSignal()

    def __init__(self, plot, parent=None):
        super(PlotWindow, self).__init__(parent)
        
        # PlotWidget to display in window
        self.pw = plot
        
        # Window appearance settings
        self.setWindowTitle(type(plot).__name__)
        self.screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.setMinimumSize(0.75 * self.screen.width(), 0.75 * self.screen.height())
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        
        # Set plot as central widget
        self.setCentralWidget(self.pw)

    def closeEvent(self, _):
        self.closeWin.emit()
        self.close()


class PlotWrapperWidget(QtWidgets.QWidget):
    """Widget that wraps PlotWidgets and implements some additional features which allow to control the PlotWidgets content.
    Also adds button to show the respective PlotWidget in a QMainWindow"""

    def __init__(self, plot=None, parent=None):
        super(PlotWrapperWidget, self).__init__(parent=parent)

        # PlotWidget to display; set size policy 
        self.pw = plot
        self.pw.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        # Main layout and sub layout for e.g. checkboxes which allow to show/hide curves in PlotWidget etc.
        self.setLayout(QtWidgets.QVBoxLayout())
        self.sub_layout = QtWidgets.QVBoxLayout()
        
        # Setup widget if class instance was initialized with plot
        if self.pw is not None:
            self._setup_widget()

    def _setup_widget(self):
        """Setup of the additional widgets to control the appearance and content of the PlotWidget"""

        _sub_layout_1 = QtWidgets.QHBoxLayout()
        _sub_layout_2 = QtWidgets.QHBoxLayout()

        # Create checkboxes in order to show/hide curves in plots
        if hasattr(self.pw, 'show_data') and hasattr(self.pw, 'curves'):
            _sub_layout_1.addWidget(QtWidgets.QLabel('Show curve(s):'))
            all_checkbox = QtWidgets.QCheckBox('All')
            all_checkbox.setFont(BOLD_FONT)
            all_checkbox.setChecked(True)
            _sub_layout_2.addWidget(all_checkbox)
            for curve in self.pw.curves:
                checkbox = QtWidgets.QCheckBox(curve)
                checkbox.setChecked(True)
                all_checkbox.stateChanged.connect(lambda _, cbx=checkbox: cbx.setChecked(all_checkbox.isChecked()))
                checkbox.stateChanged.connect(lambda v, n=checkbox.text(): self.pw.show_data(n, bool(v)))
                _sub_layout_2.addWidget(checkbox)

        else:
            logging.warning("{} has no 'show_data' method. Please implement it!".format(type(self.pw).__name__))

        _sub_layout_1.addStretch()

        # Whenever x axis is time add spinbox to change time period for which data is shown
        if hasattr(self.pw, 'update_period'):

            # Add horizontal helper line if we're looking at scrolling data plot
            unit = self.pw.plt.getAxis('left').labelUnits or '[?]'
            label = self.pw.plt.getAxis('left').labelText or 'Value'
            self.helper_line = pg.InfiniteLine(angle=0, label=label + ': {value:.2E} ' + unit)
            self.helper_line.setMovable(True)
            self.helper_line.setPen(color='w', style=pg.QtCore.Qt.DashLine, width=2)
            hl_checkbox = QtWidgets.QCheckBox('Show helper line')
            hl_checkbox.stateChanged.connect(
                lambda v: self.pw.plt.addItem(self.helper_line) if v else self.pw.plt.removeItem(self.helper_line))
            _sub_layout_1.addWidget(hl_checkbox)

            spinbox = QtWidgets.QSpinBox()
            spinbox.setRange(1, 3600)
            spinbox.setValue(self.pw._period)
            spinbox.setPrefix('Time period: ')
            spinbox.setSuffix(' s')
            spinbox.valueChanged.connect(lambda v: self.pw.update_period(v))
            _sub_layout_1.addWidget(spinbox)

        # Button to move self.pw to PlotWindow instance
        self.btn = QtWidgets.QPushButton()
        self.btn.setIcon(self.btn.style().standardIcon(QtWidgets.QStyle.SP_TitleBarMaxButton))
        self.btn.setToolTip('Open plot in window')
        self.btn.setFixedSize(25, 25)
        self.btn.clicked.connect(self.move_to_win)
        self.btn.clicked.connect(lambda: self.layout().insertStretch(1))
        self.btn.clicked.connect(lambda: self.btn.setEnabled(False))
        _sub_layout_1.addWidget(self.btn)

        self.sub_layout.addLayout(_sub_layout_1)
        self.sub_layout.addLayout(_sub_layout_2)
        
        # Insert everything into main layout
        self.layout().insertLayout(0, self.sub_layout)
        self.layout().insertWidget(1, self.pw)

    def set_plot(self, plot):
        """Set PlotWidget and set up widgets"""
        self.pw = plot
        self._setup_widget()

    def move_to_win(self):
        """Move PlotWidget to PlotWindow. When window is closed, transfer widget back to self"""
        pw = PlotWindow(plot=self.pw, parent=self)
        pw.closeWin.connect(lambda: self.layout().takeAt(1))
        pw.closeWin.connect(lambda: self.layout().insertWidget(1, self.pw))
        pw.closeWin.connect(lambda: self.btn.setEnabled(True))
        pw.show()


class IrradPlotWidget(pg.PlotWidget):
    """Base class for plot widgets"""

    def __init__(self, parent=None):
        super(IrradPlotWidget, self).__init__(parent)

        self.curves = None

    def _setup_plot(self):
        raise NotImplementedError('Please implement a _setup_plot method')

    def set_data(self):
        raise NotImplementedError('Please implement a set_data method')

    def show_data(self, curve=None, show=True):
        """Show/hide the data of curve in PlotItem. If *curve* is None, all curves are shown/hidden."""

        if not self.curves:
            raise NotImplementedError("Please define the attribute dict 'curves' and fill it with curves")

        if curve is not None and curve not in self.curves:
            logging.error('{} data not in graph. Current graphs: {}'.format(curve, ','.join(self.curves.keys())))
            return

        _curves = [curve] if curve is not None else self.curves.keys()

        for _cu in _curves:
            if show:
                if not isinstance(self.curves[_cu], pg.InfiniteLine):
                    self.legend.addItem(self.curves[_cu], _cu)
                self.plt.addItem(self.curves[_cu])
            else:
                if not isinstance(self.curves[_cu], pg.InfiniteLine):
                    self.legend.removeItem(_cu)
                self.plt.removeItem(self.curves[_cu])


class ScrollingIrradDataPlot(IrradPlotWidget):
    """PlotWidget which displays a set of irradiation data curves over time"""

    def __init__(self, channels, ro_scale=None, units=None, period=60, name=None, parent=None):
        super(ScrollingIrradDataPlot, self).__init__(parent)

        self.channels = channels
        self.ro_scale = ro_scale
        self.units = units
        self.name = name

        # Setup the main plot
        self._setup_plot()

        # Attributes for data visualization
        self._time = None  # array for timestamps
        self._data = None
        self._start = 0  # starting timestamp of each cycle
        self._timestamp = 0  # timestamp of each incoming data
        self._offset = 0  # offset for increasing cycle time
        self._idx = 0  # cycling index through time axis
        self._period = period  # amount of time for which to display data; default, displaying last 60 seconds of data
        self._filled = False  # bool to see whether the array has been filled
        self._drate = None  # data rate

    def _setup_plot(self):
        """Setting up the plot. The Actual plot (self.plt) is the underlying PlotItem of the respective PlotWidget"""

        # Get plot item and setup
        self.plt = self.getPlotItem()
        self.plt.setDownsampling(auto=True)
        self.plt.setLabel('left', text='Signal', units='V' if self.units is None else self.units['left'])

        # Title
        self.plt.setTitle('' if self.name is None else self.name)

        # Additional axis if specified
        if 'right' in self.units:
            self.plt.setLabel('right', text='Signal', units=self.units['right'])

        # X-axis is time
        self.plt.setLabel('bottom', text='Time', units='s')
        self.plt.showGrid(x=True, y=True, alpha=0.66)
        self.plt.setLimits(xMax=0)

        # Make OrderedDict of curves
        self.curves = OrderedDict([(ch, pg.PlotCurveItem(pen=MPL_COLORS[i % len(MPL_COLORS)])) for i, ch in enumerate(self.channels)])

        # Make legend entries for curves
        self.legend = pg.LegendItem(offset=(80, -50))
        self.legend.setParentItem(self.plt)

        # Show data and legend
        for ch in self.channels:
            self.show_data(ch)

    def set_data(self, data):
        """Set the data of the plot. Input data is data plus meta data"""

        # Meta data and data
        _meta, _data = data['meta'], data['data']

        # Store timestamp of current data
        self._timestamp = _meta['timestamp']

        # Set data rate if available
        if 'data_rate' in _meta:
            self._drate = _meta['data_rate']

        # Get data rate from data in order to set time axis
        if self._time is None:
            if 'data_rate' in _meta:
                self._drate = _meta['data_rate']
                shape = int(round(self._drate) * self._period + 1)
                self._time = np.zeros(shape=shape)
                self._data = OrderedDict([(ch, np.zeros(shape=shape)) for i, ch in enumerate(self.channels)])

        # Fill data
        else:

            # If we made one cycle, start again from the beginning
            if self._idx == self._time.shape[0]:
                self._idx = 0
                self._filled = True

            # If we start a new cycle, set new start timestamp and offset
            if self._idx == 0:
                self._start = self._timestamp
                self._offset = 0

            # Set time axis
            self._time[self._idx] = self._start - self._timestamp + self._offset

            # Increment index
            self._idx += 1

            # Set data in curves
            for ch in _data:
                # Shift data to the right and set 0th element
                self._data[ch][1:] = self._data[ch][:-1]
                self._data[ch][0] = _data[ch]

                if not self._filled:
                    self.curves[ch].setData(self._time[self._data[ch] != 0], self._data[ch][self._data[ch] != 0])
                else:
                    self.curves[ch].setData(self._time, self._data[ch])

    def update_scale(self, scale, axis='left', update=True):
        """Update the scale of current axis"""
        self.ro_scale = scale if update else self.ro_scale
        self.plt.getAxis(axis).setScale(scale=scale)

    def update_period(self, period):
        """Update the period of time for which the data is displayed in seconds"""

        # Update attribute
        self._period = period

        # Create new data and time
        shape = int(round(self._drate) * self._period + 1)
        new_data = OrderedDict([(ch, np.zeros(shape=shape)) for i, ch in enumerate(self.channels)])
        new_time = np.zeros(shape=shape)

        # Check whether new time and data hold more or less indices
        decreased = True if self._time.shape[0] >= shape else False

        if decreased:
            # Cut time axis
            new_time = self._time[:shape]

            # If filled before, go to 0, else go to 0 if currnt index is bigger than new shape
            if self._filled:
                self._idx = 0
            else:
                self._idx = 0 if self._idx >= shape else self._idx

            # Set wheter the array is now filled
            self._filled = True if self._idx == 0 else False

        else:
            # Extend time axis
            new_time[:self._time.shape[0]] = self._time

            # If array was filled before, go to last time, set it as offset and start from last timestamp
            if self._filled:
                self._idx = self._time.shape[0]
                self._start = self._timestamp
                self._offset = self._time[-1]

            self._filled = False

        # Set new time and data
        for ch in self.channels:
            if decreased:
                new_data[ch] = self._data[ch][:shape]
            else:
                new_data[ch][:self._data[ch].shape[0]] = self._data[ch]

        # Update
        self._time = new_time
        self._data = new_data


class RawDataPlot(ScrollingIrradDataPlot):
    """Plot for displaying the raw data of all channels of the respective ADC over time.
        Data is displayed in rolling manner over period seconds"""

    def __init__(self, daq_setup, daq_device=None, parent=None):

        # Init class attributes
        self.daq_setup = daq_setup

        # Call __init__ of ScrollingIrradDataPlot
        super(RawDataPlot, self).__init__(channels=daq_setup['channels'], units={'left': 'V', 'right': 'A'},
                                          name=type(self).__name__ + ('' if daq_device is None else ' ' + daq_device),
                                          parent=parent)

        self.plt.setRange(yRange=[-5., 5.])
        self.update_scale(scale=1e-9 / 5. * daq_setup['ro_scale'], axis='right')


class BeamCurrentPlot(ScrollingIrradDataPlot):
    """Plot for displaying the proton beam current over time. Data is displayed in rolling manner over period seconds"""

    def __init__(self, beam_current_setup=None, daq_device=None, parent=None):

        # Init class attributes
        self.beam_current_setup = beam_current_setup

        # Call __init__ of ScrollingIrradDataPlot
        super(BeamCurrentPlot, self).__init__(channels=['analog', 'digital'], units={'left': 'A', 'right': 'A'},
                                              name=type(self).__name__ + ('' if daq_device is None else ' ' + daq_device),
                                              parent=parent)

        self.plt.setLabel('left', text='Beam current', units='A')
        self.plt.hideAxis('left')
        self.plt.showAxis('right')
        self.plt.setLabel('right', text='Beam current', units='A')


class BeamPositionItem:
    """This class implements three pyqtgraph items in order to display a reticle with a circle in its intersection."""

    def __init__(self, color, name, intersect_symbol=None, horizontal=True, vertical=True):

        if not horizontal and not vertical:
            raise ValueError('At least one of horizontal or vertical beam position must be true!')

        # Whether to show horizontal and vertical lines
        self.horizontal = horizontal
        self.vertical = vertical

        # Init items needed
        self.h_shift_line = pg.InfiniteLine(angle=90)
        self.v_shift_line = pg.InfiniteLine(angle=0)
        self.intersect = pg.ScatterPlotItem()

        # Drawing style
        self.h_shift_line.setPen(color=color, style=pg.QtCore.Qt.SolidLine, width=2)
        self.v_shift_line.setPen(color=color, style=pg.QtCore.Qt.SolidLine, width=2)
        self.intersect.setPen(color=color, style=pg.QtCore.Qt.SolidLine)
        self.intersect.setBrush(color=color)
        self.intersect.setSymbol('o' if intersect_symbol is None else intersect_symbol)
        self.intersect.setSize(10)

        # Items
        self.items = []

        # Add the respective lines
        if self.horizontal and self.vertical:
            self.items = [self.intersect, self.h_shift_line, self.v_shift_line]
        elif self.horizontal:
            self.items.append(self.h_shift_line)
        else:
            self.items.append(self.v_shift_line)

        self.legend = None
        self.plotitem = None
        self.name = name

    def set_position(self, x=None, y=None):

        if x is None and y is None:
            raise ValueError('Either x or y position have to be given!')

        if self.horizontal:
            _x = x if x is not None else self.h_shift_line.value()

        if self.vertical:
            _y = y if y is not None else self.v_shift_line.value()

        if self.horizontal and self.vertical:
            self.h_shift_line.setValue(_x)
            self.v_shift_line.setValue(_y)
            self.intersect.setData([_x], [_y])
        elif self.horizontal:
            self.h_shift_line.setValue(_x)
        else:
            self.v_shift_line.setValue(_y)

    def set_plotitem(self, plotitem):
        self.plotitem = plotitem

    def set_legend(self, legend):
        self.legend = legend

    def add_to_plot(self, plotitem=None):

        if plotitem is None and self.plotitem is None:
            raise ValueError('PlotItem item needed!')

        for item in self.items:
            if plotitem is None:
                self.plotitem.addItem(item)
            else:
                plotitem.addItem(item)

    def add_to_legend(self, label=None, legend=None):

        if legend is None and self.legend is None:
            raise ValueError('LegendItem needed!')

        _lbl = label if label is not None else self.name

        if legend is None:
            self.legend.addItem(self.intersect, _lbl)
        else:
            legend.addItem(self.intersect, _lbl)

    def remove_from_plot(self, plotitem=None):

        if plotitem is None and self.plotitem is None:
            raise ValueError('PlotItem item needed!')

        for item in self.items:
            if plotitem is None:
                self.plotitem.removeItem(item)
            else:
                plotitem.removeItem(item)

    def remove_from_legend(self, label=None, legend=None):

        if legend is None and self.legend is None:
            raise ValueError('LegendItem needed!')

        _lbl = label if label is not None else self.name

        if legend is None:
            self.legend.removeItem(_lbl)
        else:
            legend.removeItem(_lbl)


class BeamPositionPlot(pg.PlotWidget):
    """
    Plot for displaying the beam position. The position is displayed from analog and digital data if available.
    """

    def __init__(self, daq_setup, daq_device=None, parent=None):
        super(BeamPositionPlot, self).__init__(parent=parent)

        # Init class attributes
        self.daq_setup = daq_setup
        self.channels = daq_setup['channels']
        self.ro_types = daq_setup['types']
        self.ro_scale = daq_setup['ro_scale']
        self.daq_device = daq_device

        # Setup the main plot
        self._setup_plot()

    def _setup_plot(self):

        # Get plot item and setup
        self.plt = self.getPlotItem()
        self.plt.setDownsampling(auto=True)
        self.plt.setTitle(type(self).__name__ if self.daq_device is None else type(self).__name__ + ' ' + self.daq_device)
        self.plt.setLabel('left', text='Vertical displacement', units='V')
        self.plt.setLabel('bottom', text='Horizontal displacement', units='V')
        self.plt.showGrid(x=True, y=True, alpha=0.66)
        self.plt.setRange(xRange=[-5., 5.], yRange=[-5., 5.])
        self.plt.setLimits(xMax=10, xMin=-10, yMax=10, yMin=-10)
        self.plt.hideButtons()
        self.plt.addLine(x=0., pen={'color': 'w', 'style': pg.QtCore.Qt.DashLine})
        self.plt.addLine(y=0., pen={'color': 'w', 'style': pg.QtCore.Qt.DashLine})
        self.legend = pg.LegendItem(offset=(80, -50))
        self.legend.setParentItem(self.plt)

        self.curves = OrderedDict()

        if any(x in self.ro_types for x in ('sem_h_shift', 'sem_v_shift')):
            sig = 'analog'
            self.curves[sig] = BeamPositionItem(color=MPL_COLORS[0], name=sig,
                                                horizontal='sem_h_shift' in self.ro_types,
                                                vertical='sem_v_shift' in self.ro_types)

        if any(all(x in self.ro_types for x in y) for y in [('sem_left', 'sem_right'), ('sem_up', 'sem_down')]):
            sig = 'digital'
            self.curves[sig] = BeamPositionItem(color=MPL_COLORS[1], name=sig,
                                                horizontal='sem_left' in self.ro_types and 'sem_right' in self.ro_types,
                                                vertical='sem_up' in self.ro_types and 'sem_down' in self.ro_types)

        # Show data and legend
        if self.curves:
            for curve in self.curves:
                self.curves[curve].set_legend(self.legend)
                self.curves[curve].set_plotitem(self.plt)
                self.show_data(curve)

    def set_data(self, data):

        # Meta data and data
        meta, pos_data = data['meta'], data['data']['position']

        for sig in pos_data:
            if sig not in self.curves:
                continue
            h_shift = None if 'h' not in pos_data[sig] else pos_data[sig]['h']
            v_shift = None if 'v' not in pos_data[sig] else pos_data[sig]['v']
            self.curves[sig].set_position(h_shift, v_shift)

    def show_data(self, curve=None, show=True):
        """Show/hide the data of channel in PlotItem. If *channel* is None, all curves are shown/hidden."""

        if curve is not None and curve not in self.curves:
            logging.error('{} data not in graph. Current graphs: {}'.format(curve, ','.join(self.curves.keys())))
            return

        _curves = [curve] if curve is not None else self.curves.keys()

        for _cu in _curves:

            if show:
                self.curves[_cu].add_to_plot()
                self.curves[_cu].add_to_legend()
            else:
                self.curves[_cu].remove_from_plot()
                self.curves[_cu].remove_from_legend()


class FluenceHist(IrradPlotWidget):
    """
        Plot for displaying the beam position. The position is displayed from analog and digital data if available.
        """

    def __init__(self, irrad_setup, daq_device=None, parent=None):
        super(FluenceHist, self).__init__(parent=parent)

        # Init class attributes
        self.irrad_setup = irrad_setup
        self.daq_device = daq_device

        # Setup the main plot
        self._setup_plot()

    def _setup_plot(self):

        # Get plot item and setup
        self.plt = self.getPlotItem()
        self.plt.setDownsampling(auto=True)
        self.plt.setTitle(type(self).__name__ if self.daq_device is None else type(self).__name__ + ' ' + self.daq_device)
        self.plt.setLabel('left', text='Proton fluence', units='cm^-2')
        self.plt.setLabel('right', text='Neutron fluence', units='cm^-2')
        self.plt.setLabel('bottom', text='Scan row')
        self.plt.getAxis('right').setScale(self.irrad_setup['kappa'])
        self.plt.getAxis('left').enableAutoSIPrefix(False)
        self.plt.getAxis('right').enableAutoSIPrefix(False)
        self.plt.setLimits(xMin=0, xMax=self.irrad_setup['n_rows'], yMin=0)
        self.legend = pg.LegendItem(offset=(80, 80))
        self.legend.setParentItem(self.plt)

        # Histogram of fluence per row
        hist_curve = pg.PlotCurveItem()
        hist_curve.setFillLevel(0.33)
        hist_curve.setBrush(pg.mkBrush(color=MPL_COLORS[0]))

        # Points at respective row positions
        hist_points = pg.ScatterPlotItem()
        hist_points.setPen(color=MPL_COLORS[2], style=pg.QtCore.Qt.SolidLine)
        hist_points.setBrush(color=MPL_COLORS[2])
        hist_points.setSymbol('o')
        hist_points.setSize(10)

        # Errorbars for points; needs to initialized with x, y args, otherwise cnnot be added to PlotItem
        hist_errors = pg.ErrorBarItem(x=np.arange(1), y=np.arange(1), beam=0.25)

        # Horizontal line indication the mean fluence over all rows
        mean_curve = pg.InfiniteLine(angle=0)
        mean_curve.setPen(color=MPL_COLORS[1], width=2)
        self.p_label = pg.InfLineLabel(mean_curve, position=0.2)
        self.n_label = pg.InfLineLabel(mean_curve, position=0.8)

        self.curves = OrderedDict([('hist', hist_curve), ('hist_points', hist_points),
                                   ('hist_errors', hist_errors), ('mean', mean_curve)])

        # Show data and legend
        for curve in self.curves:
            self.show_data(curve)

    def set_data(self, data):

        # Meta data and data
        _meta, _data = data['meta'], data['data']

        fluence = data['data']['hist']
        fluence_err = data['data']['hist_err']
        mean = np.mean(fluence)
        std = np.std(fluence)

        self.curves['hist'].setData(range(len(fluence) + 1), fluence, stepMode=True)
        self.curves['hist_points'].setData(x=np.arange(len(fluence)) + 0.5, y=fluence)
        self.curves['hist_errors'].setData(x=np.arange(len(fluence)) + 0.5, y=fluence,
                                        height=np.array(fluence_err), pen=MPL_COLORS[2])
        self.curves['mean'].setValue(mean)

        p_label = 'Mean: ({:.2E} +- {:.2E}) protons / cm^2'.format(mean, std)
        self.p_label.setFormat(p_label)
        n_label = 'Mean: ({:.2E} +- {:.2E}) neq / cm^2'.format(*[x * self.irrad_setup['kappa'] for x in (mean, std)])
        self.n_label.setFormat(n_label)
