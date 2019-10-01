from PyQt5 import QtCore, QtWidgets
from collections import OrderedDict
from irrad_control.gui.widgets import RawDataPlot, BeamPositionPlot, PlotWrapperWidget, BeamCurrentPlot, FluenceHist


class IrradMonitorTab(QtWidgets.QWidget):
    """Widget which implements a data monitor"""

    def __init__(self, setup, parent=None):
        super(IrradMonitorTab, self).__init__(parent)

        self.setup = setup

        self.monitors = ('raw', 'beam', 'fluence', 'temp')

        self.daq_tabs = QtWidgets.QTabWidget()
        self.monitor_tabs = {}

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.daq_tabs)

        self.plots = OrderedDict()

        self._init_tabs()

    def _init_tabs(self):

        for server in self.setup:

            self.plots[server] = OrderedDict()

            # Tabs per server
            self.monitor_tabs[server] = QtWidgets.QTabWidget()

            for monitor in self.monitors:

                monitor_widget = None

                if 'adc' in self.setup[server]['devices']:

                    if monitor == 'raw':

                        self.plots[server]['raw_plot'] = RawDataPlot(self.setup[server], daq_device=self.setup[server]['devices']['daq']['sem'])

                        monitor_widget = PlotWrapperWidget(self.plots[server]['raw_plot'])

                    elif monitor == 'beam':

                        monitor_widget = QtWidgets.QSplitter()
                        monitor_widget.setOrientation(QtCore.Qt.Horizontal)
                        monitor_widget.setChildrenCollapsible(False)

                        self.plots[server]['current_plot'] = BeamCurrentPlot(daq_device=self.setup[server]['devices']['daq']['sem'])
                        self.plots[server]['pos_plot'] = BeamPositionPlot(self.setup[server], daq_device=self.setup[server]['devices']['daq']['sem'])

                        beam_current_wrapper = PlotWrapperWidget(self.plots[server]['current_plot'])
                        beam_pos_wrapper = PlotWrapperWidget(self.plots[server]['pos_plot'])

                        monitor_widget.addWidget(beam_current_wrapper)
                        monitor_widget.addWidget(beam_pos_wrapper)

                if monitor_widget is not None:
                    self.monitor_tabs[server].addTab(monitor_widget, monitor.capitalize())

            self.daq_tabs.addTab(self.monitor_tabs[server], self.setup[server]['name'])

    def add_fluence_hist(self, n_rows, kappa):

        for server in self.setup:

            self.plots[server]['fluence_plot'] = FluenceHist(irrad_setup={'n_rows': n_rows, 'kappa': kappa})
            monitor_widget = PlotWrapperWidget(self.plots[server]['fluence_plot'])
            self.monitor_tabs[server].addTab(monitor_widget, 'Fluence')

