import logging
import pyqtgraph as pg
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
from collections import OrderedDict
from irrad_control import roe_output

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
        self.plot = plot
        
        # Window appearance settings
        self.setWindowTitle(type(plot).__name__)
        self.screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.setMinimumSize(0.75 * self.screen.width(), 0.75 * self.screen.height())
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        
        # Set plot as central widget
        self.setCentralWidget(self.plot)

    def closeEvent(self, _):
        self.closeWin.emit()
        self.close()


class PlotWrapperWidget(QtWidgets.QWidget):
    """Widget that wraps PlotWidgets and implements some additional features which allow to control the PlotWidgets content.
    Also adds button to show the respective PlotWidget in a QMainWindow"""

    def __init__(self, plot=None, parent=None):
        super(PlotWrapperWidget, self).__init__(parent=parent)

        # PlotWidget to display; set size policy 
        self.plot = plot
        self.plot.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        # Main layout and sub layout for e.g. checkboxes which allow to show/hide curves in PlotWidget etc.
        self.setLayout(QtWidgets.QVBoxLayout())
        self.sub_layout = QtWidgets.QHBoxLayout()
        
        # Setup widget if class instance was initialized with plot
        if self.plot is not None:
            self._setup_widget()

    def _setup_widget(self):
        """Setup of the additional widgets to control the appearance and content of the PlotWidget"""

        has_show_data_method = hasattr(self.plot, 'show_data')

        # Create checkboxes in order to show/hide curves in plots
        if has_show_data_method and hasattr(self.plot, 'curves'):
            self.sub_layout.addWidget(QtWidgets.QLabel('Show curve(s):'))
            all_checkbox = QtWidgets.QCheckBox('All')
            all_checkbox.setFont(BOLD_FONT)
            all_checkbox.setChecked(True)
            self.sub_layout.addWidget(all_checkbox)
            for curve in self.plot.curves:
                checkbox = QtWidgets.QCheckBox(curve)
                checkbox.setChecked(True)
                all_checkbox.stateChanged.connect(lambda _, cbx=checkbox: cbx.setChecked(all_checkbox.isChecked()))
                checkbox.stateChanged.connect(lambda v, n=checkbox.text(): self.plot.show_data(n, bool(v)))
                self.sub_layout.addWidget(checkbox)
        else:
            logging.warning("{} has no 'show_data' method. Please implement it!".format(type(self.plot).__name__))

        has_update_period_method = hasattr(self.plot, 'update_period')

        # Whenever x axis is time add spinbox to change time period for which data is shown
        if has_update_period_method:
            spinbox = QtWidgets.QSpinBox()
            spinbox.setRange(1, 3600)
            spinbox.setValue(self.plot._period)
            spinbox.setPrefix('Time period: ')
            spinbox.setSuffix(' s')
            spinbox.valueChanged.connect(lambda v: self.plot.update_period(v))
            self.sub_layout.addWidget(spinbox)
        
        # Button to move self.plot to PlotWindow instance
        self.btn = QtWidgets.QPushButton()
        self.btn.setIcon(self.btn.style().standardIcon(QtWidgets.QStyle.SP_TitleBarMaxButton))
        self.btn.setToolTip('Open plot in window')
        self.btn.setFixedSize(25, 25)
        self.btn.clicked.connect(self.move_to_win)
        self.btn.clicked.connect(lambda: self.layout().insertStretch(1))
        self.btn.clicked.connect(lambda: self.btn.setEnabled(False))
        self.sub_layout.addStretch()
        self.sub_layout.addWidget(self.btn)
        
        # Insert everything into main layout
        self.layout().insertLayout(0, self.sub_layout)
        self.layout().insertWidget(1, self.plot)

    def set_plot(self, plot):
        """Set PlotWidget and set up widgets"""
        self.plot = plot
        self._setup_widget()

    def move_to_win(self):
        """Move PlotWidget to PlotWindow. When window is closed, transfer widget back to self"""
        pw = PlotWindow(plot=self.plot, parent=self)
        pw.closeWin.connect(lambda: self.layout().takeAt(1))
        pw.closeWin.connect(lambda: self.layout().insertWidget(1, self.plot))
        pw.closeWin.connect(lambda: self.btn.setEnabled(True))
        pw.show()


class RawDataPlot(pg.PlotWidget):
    """Plot for displaying the raw data of all channels of the respective ADC over time.
    Data is displayed in rolling manner over period seconds"""

    def __init__(self, daq_config, period=60, parent=None):
        super(RawDataPlot, self).__init__(parent=parent)

        # Init class attributes
        self.daq_config = daq_config
        self.channels = daq_config['channels']
        self.ro_types = daq_config['types']
        self.ro_scale = daq_config['ro_scale']
        self.adc = None

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
        self.plt.setLabel('left', text='Signal', units='V')
        self.plt.setLabel('right', text='Signal', units='A')
        self.plt.getAxis('right').setScale(scale=1e-9/5. * self.ro_scale)
        self.plt.setLabel('bottom', text='Time', units='s')
        self.plt.showGrid(x=True, y=True, alpha=0.66)
        self.plt.setRange(yRange=[-5., 5.])
        self.plt.setLimits(xMax=0)

        # Make OrderedDict of curves
        self.curves = OrderedDict([(ch, pg.PlotCurveItem(pen=MPL_COLORS[i%len(MPL_COLORS)])) for i, ch in enumerate(self.channels)])

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

            self.plt.setTitle(_meta['name'] + ' raw data')

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

    def show_data(self, curve=None, show=True):
        """Show/hide the data of curve in PlotItem. If *curve* is None, all curves are shown/hidden."""

        if curve is not None and curve not in self.curves:
            logging.error('{} data not in graph. Current graphs: {}'.format(curve, ','.join(self.curves.keys())))
            return

        _curves = [curve] if curve is not None else self.curves.keys()

        for _cu in _curves:
            if show:
                self.legend.addItem(self.curves[_cu], _cu)
                self.plt.addItem(self.curves[_cu])
            else:
                self.legend.removeItem(_cu)
                self.plt.removeItem(self.curves[_cu])

    def update_scale(self, scale):
        """Update the scale of current axis"""
        self.ro_scale = scale
        self.plt.getAxis('right').setScale(scale=1e-9 / 5. * self.ro_scale)

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


class BeamPositionItem:
    """This class implements three pyqtgraph items in order to display a rectile with a circle in its intersection."""

    def __init__(self, color, name, intersect_symbol=None):

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
        self.items = [self.h_shift_line, self.v_shift_line,self.intersect]
        self.legend = None
        self.plotitem = None
        self.name = name

    def set_position(self, x, y):

        _x = x if x is not None else self.h_shift_line.value()
        _y = y if y is not None else self.v_shift_line.value()

        self.h_shift_line.setValue(_x)
        self.v_shift_line.setValue(_y)
        self.intersect.setData([_x], [_y])

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

    def __init__(self, daq_config, parent=None):
        super(BeamPositionPlot, self).__init__(parent=parent)

        # Init class attributes
        self.daq_config = daq_config
        self.channels = daq_config['channels']
        self.ro_types = daq_config['types']
        self.ro_scale = daq_config['ro_scale']
        self.adc = None

        # Possible curves
        self.d_pos = 'digital_pos'
        self.a_pos = 'analog_pos'

        # Setup the main plot
        self._setup_plot()

    def _setup_plot(self):

        # Get plot item and setup
        self.plt = self.getPlotItem()
        self.plt.setDownsampling(auto=True)
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

        # Check which channel types are present and fill curves
        if all(t in self.ro_types for t in ('sem_left', 'sem_right', 'sem_up', 'sem_down')):
            self.curves[self.d_pos] = BeamPositionItem(color=MPL_COLORS[0], name=self.d_pos)

        if all(t in self.ro_types for t in ('sem_h_shift', 'sem_v_shift')):
            self.curves[self.a_pos] = BeamPositionItem(color=MPL_COLORS[1], name=self.a_pos)

        # Show data and legend
        if self.curves:
            for curve in self.curves:
                self.curves[curve].set_legend(self.legend)
                self.curves[curve].set_plotitem(self.plt)
                self.show_data(curve)

    def set_data(self, data):

        # Meta data and data
        _meta, _data = data['meta'], data['data']

        if self.d_pos in self.curves:
            # Get indices
            l, r, u, d = (self.ro_types.index(x) for x in ('sem_left', 'sem_right', 'sem_up', 'sem_down'))

            h_shift = self._calc_shift(_data[self.channels[l]], _data[self.channels[r]], m='h')
            v_shift = self._calc_shift(_data[self.channels[u]], _data[self.channels[d]], m='v')

            self.curves[self.d_pos].set_position(h_shift, v_shift)

        if self.a_pos in self.curves:
            # Get indices
            h, v = (self.ro_types.index(x) for x in ('sem_h_shift', 'sem_v_shift'))
            h_shift, v_shift = _data[self.channels[h]], _data[self.channels[v]]
            self.curves[self.a_pos].set_position(h_shift, v_shift)

    def _calc_shift(self, a, b, m='h'):

        try:
            res = (a - b) / (a + b)
        except ZeroDivisionError:
            res = None

        # Horizontally, if we are shifted to the left the graph should move to the left, therefore * -1
        return res if res is None else -1 * res if m == 'h' else res

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


class BeamCurrentPlot(pg.PlotWidget):
    pass


class FluenceMap(pg.ViewBox):
    pass
