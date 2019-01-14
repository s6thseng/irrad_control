import logging
import pyqtgraph as pg
import numpy as np
from irrad_control import roe_output

# Matplotlib first 8 default colors
MPL_COLORS = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
              (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]


class RawDataGraph(pg.PlotWidget):
    """
    Plot for displaying the raw data of all channels of the respective ADC over time.
    Data is displayed in rolling manner over period seconds
    """

    def __init__(self, daq_config, period=10, parent=None):
        super(RawDataGraph, self).__init__(parent=parent)

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
        self._idx = 0  # cycling index through time axis
        self._period = period  # amount of time for which to display data; default, displaying last 60 seconds of data
        self._filled = False  # bool to see whether the array has been filled
        self._drate = None

    def _setup_plot(self):

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

        # Make dict of curves
        self.curves = dict([(ch, pg.PlotCurveItem(pen=MPL_COLORS[i%len(MPL_COLORS)])) for i, ch in enumerate(self.channels)])

        # Make legend entries for curves
        self.legend = pg.LegendItem(offset=(80, -50))
        self.legend.setParentItem(self.plt)

        # Show data and legend
        for ch in self.channels:
            self.show_data(ch)

    def set_data(self, data):

        # Meta data and data
        _meta, _data = data['meta'], data['data']

        timestamp = _meta['timestamp']

        # Get data rate from data in order to set time axis
        if self._time is None:

            if 'data_rate' in _meta:
                self._drate = _meta['data_rate']
                shape = int(round(self._drate) * self._period + 1)
                self._time = np.zeros(shape=shape)
                self._data = dict([(ch, np.zeros(shape=shape)) for i, ch in enumerate(self.channels)])

            self.plt.setTitle(_meta['name'] + ' raw data')

        # Fill data
        else:

            if self._idx == self._time.shape[0]:
                self._idx = 0
                self._filled = True

            if self._idx == 0:
                self._start = timestamp

            # Set time axis
            self._time[self._idx] = self._start - timestamp
            self._idx += 1

            # Set data in curves
            for ch in _data:
                self._data[ch][1:] = self._data[ch][:-1]
                self._data[ch][0] = _data[ch]

                if not self._filled:
                    self.curves[ch].setData(self._time[self._data[ch] != 0], self._data[ch][self._data[ch] != 0])
                else:
                    self.curves[ch].setData(self._time, self._data[ch])

    def show_data(self, channel, show=True):

        if channel not in self.channels:
            logging.error('{} data not in graph. Current graphs: {}'.format(channel, ','.join(self.channels)))
            return

        if show:
            self.legend.addItem(self.curves[channel], channel)
            self.plt.addItem(self.curves[channel])
        else:
            self.legend.removeItem(channel)
            self.plt.removeItem(self.curves[channel])

    def update_scale(self, scale):
        self.ro_scale = scale
        self.plt.getAxis('right').setScale(scale=1e-9 / 5. * self.ro_scale)

    def update_period(self, period):

        # Update attribute
        self._period = period

        # Create new data and time
        shape = int(round(self._drate) * self._period + 1)
        new_data = dict([(ch, np.zeros(shape=shape)) for i, ch in enumerate(self.channels)])
        new_time = np.zeros(shape=shape)

        # Check whether new time and data hold more or less indices
        decreased = True if self._time.shape[0] >= shape else False

        if decreased:  # THIS WORKS
            new_time = self._time[:shape]
            self._idx = 0 if self._idx >= shape else self._idx

        else:  # THIS ONLY WORKS IF ARRAYS HAVE NOT BEEN FILLED: TODO: Find out why...
            #new_time[:self._time.shape[0]] = self._time
            #if self._filled:
            #    self._idx = self._time.shape[0]
            self._filled = False
            self._idx = 0

        for ch in self.channels:
            if decreased:
                new_data[ch] = self._data[ch][:shape]
            #else:
            #    new_data[ch][:self._data[ch].shape[0]] = self._data[ch]

        self._time = new_time
        self._data = new_data


class BeamPositionItem:
    """This class implements three pyqtgraph items in order to display a rectile with a circle in its intersection."""

    def __init__(self, color, name, intersect_symbol=None):

        # Init items needed
        self.h_line = pg.InfiniteLine(angle=0)
        self.v_line = pg.InfiniteLine(angle=90)
        self.intersect = pg.ScatterPlotItem()

        # Drawing style
        self.h_line.setPen(color=color, style=pg.QtCore.Qt.DashLine, width=2)
        self.v_line.setPen(color=color, style=pg.QtCore.Qt.DashLine, width=2)
        self.intersect.setPen(color=color, style=pg.QtCore.Qt.SolidLine)
        self.intersect.setSymbol('o' if intersect_symbol is None else intersect_symbol)
        self.intersect.setSize(2)

        # Items
        self.items = [self.h_line, self.v_line, self.intersect]
        self.legend = None
        self.plotitem = None
        self.name = name

    def set_position(self, x, y):

        self.h_line.setPos(x)
        self.v_line.setPos(y)
        self.intersect.setData([x], [y])

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

    def remove_from_legend(self, label, legend=None):

        if legend is None and self.legend is None:
            raise ValueError('LegendItem needed!')

        _lbl = label if label is not None else self.name

        if legend is None:
            self.legend.removeItem(_lbl)
        else:
            legend.removeItem(_lbl)


class BeamPositionGraph(pg.PlotWidget):
    """
    Plot for displaying the beam position. The position is displayed from analog and digital data if available.
    """

    def __init__(self, daq_config, parent=None):
        super(BeamPositionGraph, self).__init__(parent=parent)

        # Init class attributes
        self.daq_config = daq_config
        self.channels = daq_config['channels']
        self.ro_types = daq_config['types']
        self.ro_scale = daq_config['ro_scale']
        self.adc = None

        # Make curves
        self.plots = ('Digital', 'Analog')

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

        self.curves = {}
        for plot in self.plots:
            curves = []
            pg.ScatterPlotItem()

        # Make dict of curves
        self.curves = dict([(ch, pg.PlotCurveItem(pen=MPL_COLORS[i % len(MPL_COLORS)])) for i, ch in enumerate(self.channels)])

        # Make legend entries for curves
        self.legend = pg.LegendItem(offset=(80, -50))
        self.legend.setParentItem(self.plt)

        # Show data and legend
        for ch in self.channels:
            self.show_data(ch)

    def _mk_pos_curves(self):

        pos_curves = {}
        for i, plt in enumerate(self.plots):

            # Each position plot consist of a reticle (two crossed lines) and a circle at their intersect
            h_line = pg.InfiniteLine(angle=0)
            v_line = pg.InfiniteLine(angle=90)
            intersect = pg.ScatterPlotItem()

            # Drawing stuff
            h_line.setPen(color=MPL_COLORS[i], style=pg.QtCore.Qt.DashLine, width=2)
            v_line.setPen(color=MPL_COLORS[i], style=pg.QtCore.Qt.DashLine, width=2)
            intersect.setPen(color=MPL_COLORS[i], style=pg.QtCore.Qt.SolidLine)
            intersect.setSymbol('o')
            intersect.setSize(2)

            pos_items = {'h_line': pg.InfiniteLine(), 'v_line': pg.InfiniteLine(), 'intersect': pg.ScatterPlotItem()}

    def show_data(self, curve, show=True):

        if curve not in self.curve:
            logging.error('{} data not in graph. Current graphs: {}'.format(curve, ','.join(self.curve)))
            return

        if show:
            self.legend.addItem(self.curves[curve], curve)
            self.plt.addItem(self.curves[curve])
        else:
            self.legend.removeItem(curve)
            self.plt.removeItem(self.curves[curve])


class BeamCurrentGraph(pg.PlotWidget):
    pass


class FluenceMap(pg.ViewBox):
    pass
