from PyQt5 import QtCore, QtWidgets
from collections import OrderedDict
from irrad_control.gui_widgets.plot_widgets import RawDataPlot, BeamPositionPlot, PlotWrapperWidget


class IrradMonitor(QtWidgets.QWidget):
    """Widget which implements a data monitor"""

    def __init__(self, daq_config, parent=None):
        super(IrradMonitor, self).__init__(parent)

        self.daq_config = daq_config

        self.monitors = ('raw', 'interpreter')

        self.daq_tabs = QtWidgets.QTabWidget()

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.daq_tabs)

        self.plots = OrderedDict()

        self._init_tabs()

    def _init_tabs(self):

        for adc in self.daq_config:

            self.plots[adc] = OrderedDict()

            # Tabs per adc/daq device
            monitor_tabs = QtWidgets.QTabWidget()

            for monitor in self.monitors:

                if monitor == 'raw':
                    monitor_widget = QtWidgets.QSplitter()
                    monitor_widget.setOrientation(QtCore.Qt.Horizontal)
                    monitor_widget.setChildrenCollapsible(False)

                    self.plots[adc]['raw_plot'] = RawDataPlot(self.daq_config[adc])
                    self.plots[adc]['pos_plot'] = BeamPositionPlot(self.daq_config[adc])

                    raw_wrapper = PlotWrapperWidget(self.plots[adc]['raw_plot'])
                    pos_wrapper = PlotWrapperWidget(self.plots[adc]['pos_plot'])

                    monitor_widget.addWidget(raw_wrapper)
                    monitor_widget.addWidget(pos_wrapper)
                else:
                    monitor_widget = QtWidgets.QWidget()

                monitor_tabs.addTab(monitor_widget, monitor.capitalize())

            self.daq_tabs.addTab(monitor_tabs, adc)
