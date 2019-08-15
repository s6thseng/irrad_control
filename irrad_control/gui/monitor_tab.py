from PyQt5 import QtCore, QtWidgets
from collections import OrderedDict
from irrad_control.gui_widgets.plot_widgets import RawDataPlot, BeamPositionPlot, PlotWrapperWidget, BeamCurrentPlot, FluenceHist


class IrradMonitor(QtWidgets.QWidget):
    """Widget which implements a data monitor"""

    def __init__(self, daq_setup, parent=None):
        super(IrradMonitor, self).__init__(parent)

        self.daq_setup = daq_setup

        self.monitors = ('raw', 'beam', 'fluence')

        self.daq_tabs = QtWidgets.QTabWidget()
        self.monitor_tabs = {}

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.daq_tabs)

        self.plots = OrderedDict()

        self._init_tabs()

    def _init_tabs(self):

        for adc in self.daq_setup:

            self.plots[adc] = OrderedDict()

            # Tabs per adc/daq device
            self.monitor_tabs[adc] = QtWidgets.QTabWidget()

            for monitor in self.monitors:

                if monitor == 'fluence':
                    continue

                if monitor == 'raw':

                    self.plots[adc]['raw_plot'] = RawDataPlot(self.daq_setup[adc], daq_device=adc)

                    monitor_widget = PlotWrapperWidget(self.plots[adc]['raw_plot'])

                elif monitor == 'beam':

                    monitor_widget = QtWidgets.QSplitter()
                    monitor_widget.setOrientation(QtCore.Qt.Horizontal)
                    monitor_widget.setChildrenCollapsible(False)

                    self.plots[adc]['current_plot'] = BeamCurrentPlot(daq_device=adc)
                    self.plots[adc]['pos_plot'] = BeamPositionPlot(self.daq_setup[adc], daq_device=adc)

                    beam_current_wrapper = PlotWrapperWidget(self.plots[adc]['current_plot'])
                    beam_pos_wrapper = PlotWrapperWidget(self.plots[adc]['pos_plot'])

                    monitor_widget.addWidget(beam_current_wrapper)
                    monitor_widget.addWidget(beam_pos_wrapper)

                #elif monitor == 'fluence':
                #    self.plots[adc]['fluence_plot'] = FluenceHist(irrad_setup={'n_rows': 50, 'kappa': 3})
                #    monitor_widget = PlotWrapperWidget(self.plots[adc]['fluence_plot'])

                self.monitor_tabs[adc].addTab(monitor_widget, monitor.capitalize())

            self.daq_tabs.addTab(self.monitor_tabs[adc], adc)

    def add_fluence_hist(self, n_rows, kappa):

        for adc in self.daq_setup:

            self.plots[adc]['fluence_plot'] = FluenceHist(irrad_setup={'n_rows': n_rows, 'kappa': kappa})
            monitor_widget = PlotWrapperWidget(self.plots[adc]['fluence_plot'])
            self.monitor_tabs[adc].addTab(monitor_widget, 'Fluence')

