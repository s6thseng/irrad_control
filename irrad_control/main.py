import sys
import time
import logging
import platform
import zmq
import yaml
from collections import OrderedDict
from email import message_from_string
from pkg_resources import get_distribution, DistributionNotFound
from PyQt5 import QtCore, QtWidgets, QtGui
from threading import Event

# Package imports
from irrad_control.utils import CustomHandler, LoggingStream, log_levels, Worker, ProcessManager
from irrad_control.gui.widgets import DaqInfoWidget
from irrad_control.gui.tabs import IrradSetupTab, IrradControlTab, IrradMonitorTab


PROJECT_NAME = 'Irrad Control'
GUI_AUTHORS = 'Pascal Wolf'
MINIMUM_RESOLUTION = (1366, 768)

try:
    pkgInfo = get_distribution('irrad_control').get_metadata('PKG-INFO')
    AUTHORS = message_from_string(pkgInfo)['Author']
except (DistributionNotFound, KeyError):
    AUTHORS = 'Not defined'

# needed to dump OrderedDict into file, representer for ordereddict (https://stackoverflow.com/a/8661021)
represent_dict_order = lambda self, data: self.represent_mapping('tag:yaml.org,2002:map', data.items())
yaml.add_representer(OrderedDict, represent_dict_order)


class IrradControlWin(QtWidgets.QMainWindow):
    """Inits the main window of the irrad_control software."""

    # PyQt signals
    data_received = QtCore.pyqtSignal(dict)  # Signal for data
    reply_received = QtCore.pyqtSignal(dict)  # Signal for reply
    log_received = QtCore.pyqtSignal(dict)  # Signal for log

    def __init__(self, parent=None):
        super(IrradControlWin, self).__init__(parent)

        # Setup dict of the irradiation; is set when setup tab is completed
        self.setup = None
        
        # Needed in ordeer to stop helper threads
        self.stop_recv_data = Event()
        self.stop_recv_log = Event()
        self.daq_started = False
        self.shutdown_confirmed = False
        
        # ZMQ context; THIS IS THREADSAFE! SOCKETS ARE NOT!
        # EACH SOCKET NEEDS TO BE CREATED WITHIN ITS RESPECTIVE THREAD/PROCESS!
        self.context = zmq.Context()
        
        # QThreadPool manages GUI threads on its own; every runnable started via start(runnable) is auto-deleted after.
        self.threadpool = QtCore.QThreadPool()

        # Server process and hardware that can receive commands using self.send_cmd method
        self._targets = ('server', 'adc', 'stage', 'temp', 'interpreter')

        # Interpreter process
        self.interpreter = None
        self.proc_mngr = None
        
        # Connect signals
        self.data_received.connect(lambda data: self.handle_data(data))
        self.reply_received.connect(lambda reply: self.handle_reply(reply))
        self.log_received.connect(lambda log: self.handle_log(log))

        # Tab widgets
        self.setup_tab = None
        self.control_tab = None
        self.monitor_tab = None

        # Init user interface
        self._init_ui()
        self._init_logging()
        
    def _init_ui(self):
        """
        Initializes the user interface and displays "Hello"-message
        """

        # Main window settings
        self.setWindowTitle(PROJECT_NAME)
        self.screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.setMinimumSize(MINIMUM_RESOLUTION[0], MINIMUM_RESOLUTION[1])
        self.resize(self.screen.width(), self.screen.height())
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Create main layout
        self.main_widget = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QVBoxLayout(self.main_widget)
        self.setCentralWidget(self.main_widget)

        # Add QTabWidget for tab_widget
        self.tabs = QtWidgets.QTabWidget()

        # Main splitter
        self.main_splitter = QtWidgets.QSplitter()
        self.main_splitter.setOrientation(QtCore.Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)

        # Sub splitter for log and displaying raw data as it comes in
        self.sub_splitter = QtWidgets.QSplitter()
        self.sub_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.sub_splitter.setChildrenCollapsible(False)

        # Add to main layout
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.addWidget(self.sub_splitter)
        self.main_layout.addWidget(self.main_splitter)

        # Init widgets and add to main windowScatterPlotItem
        self._init_menu()
        self._init_tabs()
        self._init_log_dock()
        
        self.sub_splitter.setSizes([int(1. / 3. * self.width()), int(2. / 3. * self.width())])
        self.main_splitter.setSizes([int(0.8 * self.height()), int(0.2 * self.height())])
        
    def _init_menu(self):
        """Initialize the menu bar of the IrradControlWin"""

        self.file_menu = QtWidgets.QMenu('&File', self)
        self.file_menu.addAction('&Quit', self.file_quit, QtCore.Qt.CTRL + QtCore.Qt.Key_Q)
        self.menuBar().addMenu(self.file_menu)

        self.settings_menu = QtWidgets.QMenu('&Settings', self)
        self.settings_menu.addAction('&Connections')
        self.settings_menu.addAction('&Data path')
        self.menuBar().addMenu(self.settings_menu)

        self.appearance_menu = QtWidgets.QMenu('&Appearance', self)
        self.appearance_menu.setToolTipsVisible(True)
        self.appearance_menu.addAction('&Show/hide log', self.handle_log_ui, QtCore.Qt.CTRL + QtCore.Qt.Key_L)
        self.menuBar().addMenu(self.appearance_menu)

    def _init_tabs(self):
        """
        Initializes the tabs for the control window
        """

        # Add tab_widget and widgets for the different analysis steps
        self.tab_order = ('Setup', 'Control', 'Monitor')

        # Store tabs
        tw = {}

        # Initialize each tab
        for name in self.tab_order:

            if name == 'Setup':
                self.setup_tab = IrradSetupTab(parent=self)
                self.setup_tab.setupCompleted.connect(lambda setup: self._init_setup(setup))
                tw[name] = self.setup_tab
            else:
                tw[name] = QtWidgets.QWidget()

            self.tabs.addTab(tw[name], name)
            self.tabs.setTabEnabled(self.tabs.indexOf(tw[name]), name in ['Setup'])

    def _init_setup(self, setup):

        self.daq_started = True

        # Store setup
        self.setup = setup

        # Adjust logging level
        logging.getLogger().setLevel(setup['session']['loglevel'])

        # Update tab widgets accordingly
        self.update_tabs()

        # Init daq info widget
        self._init_daq_dock()

        # Start receiving data and log
        self._init_threads()

        # Init subprocesses
        self._init_subprocesses()

    def _init_log_dock(self):
        """Initializes corresponding log dock"""

        # Widget to display log in, we only want to read log
        self.log_console = QtWidgets.QPlainTextEdit()
        self.log_console.setReadOnly(True)
        
        # Dock in which text widget is placed to make it closable without losing log content
        self.log_dock = QtWidgets.QDockWidget()
        self.log_dock.setWidget(self.log_console)
        self.log_dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.log_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable)
        self.log_dock.setWindowTitle('Log')

        # Add to main layout
        self.sub_splitter.addWidget(self.log_dock)
        self.handle_log_ui()

    def _init_daq_dock(self):
        """Initializes corresponding daq info dock"""
        # Make raw data widget
        self.daq_info_widget = DaqInfoWidget(self.setup['daq'])

        # Dock in which text widget is placed to make it closable without losing log content
        self.daq_info_dock = QtWidgets.QDockWidget()
        self.daq_info_dock.setWidget(self.daq_info_widget)
        self.daq_info_dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.daq_info_dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.daq_info_dock.setWindowTitle('DAQ Info')

        # Add to main layout
        self.sub_splitter.addWidget(self.daq_info_dock)

    def _init_logging(self, loglevel=logging.INFO):
        """Initializes a custom logging handler and redirects stdout/stderr"""

        # Store loglevel of remote processes; subprocesses send log level and message separately
        self._remote_loglevel = 0
        self._loglevel_names = [lvl for lvl in log_levels.keys() if isinstance(lvl, str)]

        # Set logging level
        logging.getLogger().setLevel(loglevel)

        # Create logger instance
        self.logger = CustomHandler(self.main_widget)
        self.logger.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        # Add custom logger
        logging.getLogger().addHandler(self.logger)

        # Connect logger signal to logger console
        LoggingStream.stdout().messageWritten.connect(lambda msg: self.log_console.appendPlainText(msg))
        LoggingStream.stderr().messageWritten.connect(lambda msg: self.log_console.appendPlainText(msg))
        
        logging.info('Started "irrad_control" on %s' % platform.system())

    def handle_log(self, log_dict):

        if 'level' in log_dict:
            self._remote_loglevel = log_dict['level']

        elif 'log' in log_dict:
            logging.log(level=self._remote_loglevel, msg=log_dict['log'])

    def _init_subprocesses(self):

        # Class to manage the server, interpreter and additional subprocesses
        self.proc_mngr = ProcessManager()

        # Loop over all server(s), connect to the server(s) and launch worker for configuration
        server_config_workers = {}
        for hostname in self.setup['tcp']['ip']['server']:
            # Connect
            self.proc_mngr.connect_to_server(hostname=hostname, username='pi')

            # Prepare server in QThread on init
            server_config_workers[hostname] = Worker(func=self.proc_mngr.configure_server, args=(hostname, ))

            # Connect workers finish signal to starting process on server
            for con in [lambda h=hostname: self.proc_mngr.start_server_process(h, self.setup['tcp']['port']['cmd']),
                        lambda h=hostname: self.send_cmd(hostname=h, target='server', cmd='start', cmd_data=self.setup)
                        ]:
                server_config_workers[hostname].signals.finished.connect(con)

            # Launch worker on QThread
            self.threadpool.start(server_config_worker[hostname])

        # Launch interpreter process
        self.proc_mngr.start_interpreter_process(self.setup['tcp']['port']['cmd'])
            
    def _init_threads(self):       
                
        # Fancy QThreadPool and QRunnable approach
        recv_workers = {'recv_data': Worker(func=self.recv_data),
                        'recv_log': Worker(func=self.recv_log)}
        
        for _worker in recv_workers:
            self.threadpool.start(recv_workers[_worker])
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def update_tabs(self):

        current_tab = self.tabs.currentIndex()

        # Create missing tabs
        self.control_tab = IrradControl(irrad_setup=self.setup, parent=self.tabs)
        self.monitor_tab = IrradMonitor(daq_setup=self.setup['daq'], parent=self.tabs)

        # Connect control tab
        self.control_tab.sendCmd.connect(lambda cmd_dict: self.send_cmd(**cmd_dict))
        self.control_tab.btn_auto_zero.clicked.connect(lambda: self.interpreter.auto_zero.set())

        # Make temporary dict for updated tabs
        tmp_tw = {'Control': self.control_tab, 'Monitor': self.monitor_tab}

        for tab in self.tab_order:
            if tab in tmp_tw.keys():

                # Remove old tab, insert updated tab at same index and set status
                self.tabs.removeTab(self.tab_order.index(tab))
                self.tabs.insertTab(self.tab_order.index(tab), tmp_tw[tab], tab)

        # Set the tab index to stay at the same tab after replacing old tabs
        self.tabs.setCurrentIndex(current_tab)
    
    def handle_data(self, data):

        adc = data['meta']['name']

        # Check whether data is interpreted
        if data['meta']['type'] == 'raw':

            self.daq_info_widget.update_raw_data(data)

            self.monitor_tab.plots[adc]['raw_plot'].set_data(data)

        # Check whether data is interpreted
        elif data['meta']['type'] == 'beam':
            self.daq_info_widget.update_beam_current(data)
            self.monitor_tab.plots[adc]['pos_plot'].set_data(data)
            _data = {'meta': data['meta'], 'data': data['data']['current']}
            self.monitor_tab.plots[adc]['current_plot'].set_data(_data)
            self.control_tab.beam_current = data['data']['current']['analog']
            self.control_tab.check_no_beam()

        # Check whether data is interpreted
        elif data['meta']['type'] == 'fluence':
            self.monitor_tab.plots[adc]['fluence_plot'].set_data(data)

            hist, hist_err = (data['data'][x] for x in ('hist', 'hist_err'))

            lower_mean_f = sum([hist[i] - hist_err[i] for i in range(len(hist))]) / float(len(hist))

            if lower_mean_f >= self.control_tab.aim_fluence:
                self.send_cmd('stage', 'finish')

            self.control_tab.update_fluence(hist[self.control_tab.scan_params['row']],  type_='row')

            if self.control_tab.scan_params['row'] in (0, self.control_tab.scan_params['n_rows'] - 1):
                mean_fluence = sum(hist) / len(hist)
                self.control_tab.update_fluence(mean_fluence, type_='scan')
                est_n_scans = (self.control_tab.aim_fluence - mean_fluence) / (self.control_tab.beam_current / (1.60217733e-19 * self.control_tab.scan_params['scan_speed'] * self.control_tab.scan_params['step_size'] * 1e-2))
                self.control_tab.update_n_scans(int(est_n_scans))

        elif data['meta']['type'] == 'stage':

            if data['data']['status'] == 'start':
                self.control_tab.update_position([data['data']['x_start'], data['data']['y_start']])
                self.control_tab.update_scan_parameters(scan=data['data']['scan'], row=data['data']['row'],
                                                        scan_speed=data['data']['speed'])
                self.control_tab.update_stage_status('Scanning...')

            elif data['data']['status'] == 'stop':
                self.control_tab.update_position([data['data']['x_stop'], data['data']['y_stop']])
                self.control_tab.update_stage_status('Turning')

            elif data['data']['status'] == 'finished':

                self.control_tab.scan_actions(data['data']['status'])
            
    def send_cmd(self, hostname, target, cmd, cmd_data=None):
        """Send a command *cmd* to a target *target* running within the server or interpreter process.
        The command can have respective data *cmd_data*. Targets must be listed in self._targets."""

        if target not in self._targets:
            msg = '{} not in known by command targets. Known targets: {}'.format(target, ', '.join(self._targets))
            logging.error(msg)
            return

        cmd_dict = {'target': target, 'cmd': cmd, 'data': cmd_data}
        cmd_worker = Worker(self._send_cmd_get_reply, hostname, cmd_dict)
        self.threadpool.start(cmd_worker)

    def _send_cmd_get_reply(self, hostname, cmd_dict):
        """Sending a command to the server and waiting for its reply. This runs on a separate QThread due
        to the blocking nature of the recv() method of sockets. *cmd_dict* contains the target, cmd and cmd_data."""

        # Spawn socket to send request to server and connect
        server_req = self.context.socket(zmq.REQ)
        server_req.connect(self._tcp_addr(self.setup['tcp']['port']['cmd'], hostname))

        # Send command dict and wait for reply
        server_req.send_json(cmd_dict)
        server_reply = server_req.recv_json()

        # Emit the received reply in pyqt signal and close socket
        self.reply_received.emit(server_reply)
        server_req.close()

    def handle_reply(self, reply_dict):

        reply = reply_dict['reply']
        _type = reply_dict['type']
        sender = reply_dict['sender']
        reply_data = None if 'data' not in reply_dict else reply_dict['data']

        if _type == 'STANDARD':

            if sender == 'server':

                if reply == 'pid':

                    self.server.set_server_pid(reply_data)
                    self.tabs.setCurrentIndex(self.tabs.indexOf(self.monitor_tab))

                    # Send command to find where stage is and what the speeds are
                    self.send_cmd('stage', 'pos')
                    self.send_cmd('stage', 'get_speed')

                elif reply == 'shutdown':

                    self.shutdown_confirmed = True

                    logging.debug("Server shut down")

            elif sender == 'stage':

                if reply == 'pos':
                    self.control_tab.update_position(reply_data)

                elif reply == 'get_speed':
                    self.control_tab.update_speed(reply_data)

                elif reply == 'prepare':
                    self.control_tab.update_scan_parameters(**reply_data)
                    self.monitor_tab.add_fluence_hist(**{'kappa': self.setup['daq'][self.setup['daq'].keys()[0]]['hardness_factor'],
                                                         'n_rows': reply_data['n_rows']})
                    self.send_cmd(target='stage', cmd='scan')
                    self.control_tab.scan_actions('started')

                    est_n_scans = self.control_tab.aim_fluence / (self.control_tab.beam_current / (1.60217733e-19 * self.control_tab.scan_params['scan_speed'] * self.control_tab.scan_params['step_size'] * 1e-2))
                    self.control_tab.update_n_scans(int(est_n_scans))

                elif reply == 'finish':

                    logging.info("Finishing scan!")

                elif reply == 'no_beam':

                    if reply_data:
                        logging.debug("No beam event set")
                    else:
                        logging.debug("No beam event cleared")

        elif _type == 'ERROR':
            msg = '{} error occured: {}'.format(sender.capitalize(), reply)
            logging.error(msg)
            self.log_dock.setVisible(True)

        else:
            logging.info('Received reply {} from {}'.format(reply, sender))

    def recv_data(self):
        
        # Data subscriber
        data_sub = self.context.socket(zmq.SUB)

        # Connect to data from remote server and local interpreter process
        for ip in self.setup['tcp']['ip']['server'] + ['localhost']:
            data_sub.connect(self._tcp_addr(self.setup['tcp']['port']['data'], ip=ip))

        # Connect to stage data
        data_sub.connect(self._tcp_addr(self.setup['tcp']['port']['stage'], ip=self.setup['tcp']['ip']['server']))

        data_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        data_timestamps = {}
        
        logging.info('Data receiver ready')
        
        while not self.stop_recv_data.is_set():
            
            data = data_sub.recv_json()
            dtype = data['meta']['type']

            if dtype not in data_timestamps:
                data_timestamps[dtype] = time.time()
            else:
                now = time.time()
                drate = 1. / (now - data_timestamps[dtype])
                data_timestamps[dtype] = now
                data['meta']['data_rate'] = drate

            self.data_received.emit(data)
            
    def recv_log(self):
        
        # Log subscriber
        log_sub = self.context.socket(zmq.SUB)

        # Connect to log messages from remote server and local interpreter process
        for ip in (self.setup['tcp']['ip']['server'], 'localhost'):
            log_sub.connect(self._tcp_addr(self.setup['tcp']['port']['log'], ip=ip))

        log_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        logging.info('Log receiver ready')
        
        while not self.stop_recv_log.is_set():
            log = log_sub.recv()
            if log:
                log_dict = {}

                if log.upper() in self._loglevel_names:
                    log_dict['level'] = getattr(logging, log.upper(), None)
                else:
                    log_dict['log'] = log.strip()

                self.log_received.emit(log_dict)

    def handle_messages(self, message, ms=4000):
        """Handles messages from the tabs shown in QMainWindows statusBar"""

        self.statusBar().showMessage(message, ms)

    def handle_log_ui(self):
        """Handle whether log widget is visible or not"""

        if self.log_dock.isVisible():
            self.log_dock.setVisible(False)
        else:
            self.log_dock.setVisible(True)

    def check_resolution(self):
        """Checks for resolution and gives pop-up warning if too low"""

        # Show message box with warning if screen resolution is lower than required
        if self.screen.width() < MINIMUM_RESOLUTION[0] or self.screen.height() < MINIMUM_RESOLUTION[1]:
            msg = "Your screen resolution (%d x %d) is below the required minimum resolution of %d x %d." \
                  " This may affect the appearance!" % (self.screen.width(), self.screen.height(),
                                                        MINIMUM_RESOLUTION[0], MINIMUM_RESOLUTION[1])
            title = "Screen resolution low"
            msg_box = QtWidgets.QMessageBox.information(self, title, msg, QtWidgets.QMessageBox.Ok)
            
    def _clean_up(self):

        # Stop interpreter and terminate
        self.interpreter.shutdown()
        self.interpreter.join()

        # Shutdown server process on host; timeout 3 secs
        start = time.time()
        while not self.shutdown_confirmed and time.time() - start < 3:
            self.send_cmd('server', 'shutdown')
            QtWidgets.QApplication.processEvents()
            time.sleep(0.1)

        # Stop receiver threads
        self.stop_recv_data.set()
        self.stop_recv_log.set()

        # Clear threadpool
        self.threadpool.clear()

    def file_quit(self):

        if self.daq_started:
            self._clean_up()

        self.close()

    def closeEvent(self, _):
        self.file_quit()


def main():
    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setPointSize(11)
    app.setFont(font)
    icw = IrradControlWin()
    icw.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
