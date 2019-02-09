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

# Package imports
from irrad_control.utils.logger import IrradLogger, LoggingStream
from irrad_control.utils.worker import Worker
from irrad_control.utils.server_manager import ServerManager
from irrad_control.gui_widgets.daq_info_widget import DaqInfoWidget
from irrad_control.gui_widgets.monitor_tab import IrradMonitor
from irrad_control.gui_widgets.setup_tab import IrradSetup
from irrad_control.interpreter import IrradInterpreter


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
    log_received = QtCore.pyqtSignal(str)  # Signal for log

    def __init__(self, parent=None):
        super(IrradControlWin, self).__init__(parent)

        # Setupd dict of the irradiation; is set when setup tab is completed
        self.setup = None
        
        # Needed in ordeer to stop helper threads
        self.receive_data = True
        self.receive_log = True
        self.daq_started = False
        
        # ZMQ context; THIS IS THREADSAFE! SOCKETS ARE NOT!
        # EACH SOCKET NEEDS TO BE CREATED WITHIN ITS RESPECTIVE THREAD/PROCESS!
        self.context = zmq.Context()
        
        # QThreadPool manages GUI threads on its own; every runnable started via start(runnable) is auto-deleted after.
        self.threadpool = QtCore.QThreadPool()

        # Server process and hardware that can receive commands using self.send_cmd method
        self.server_targets = ('server', 'adc', 'stage')

        # Interpreter process
        self.interpreter = IrradInterpreter()
        
        # Connect signals
        self.data_received.connect(lambda data: self.handle_data(data))
        self.reply_received.connect(lambda reply: self.handle_reply(reply))
        self.log_received.connect(lambda log: logging.info(log))

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
        self.resize(0.8 * self.screen.width(), 0.8 * self.screen.height())
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
        
        self.sub_splitter.setSizes([int(0.45 * self.width()), int(0.55 * self.width())])
        self.main_splitter.setSizes([int(2. / 3. * self.height()), int(1. / 3. * self.height())])
        
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
                self.setup_tab = IrradSetup(parent=self)
                self.setup_tab.setupCompleted.connect(lambda setup: self._init_setup(setup))
                self.setup_tab.setupCompleted.connect(self.setup_tab.set_read_only)

                tw[name] = self.setup_tab
            else:
                tw[name] = QtWidgets.QWidget()

            self.tabs.addTab(tw[name], name)

    def _init_setup(self, setup):

        self.daq_started = True

        # Store setup
        self.setup = setup

        # Update tab widgets accordingly
        self.update_tabs()

        # Init daq info widget
        self._init_daq_dock()

        # Start logging data
        self._init_data_log()

        # Start receiving data and log
        self._init_threads()

        # Init server
        self._init_server()

        # Init interpreter
        self.interpreter.update_setup(setup)
        self.interpreter.start()

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

        # Set logging level
        logging.getLogger().setLevel(loglevel)

        # Create logger instance
        self.logger = IrradLogger(self.main_widget)
        self.logger.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        # Add custom logger
        logging.getLogger().addHandler(self.logger)

        # Connect logger signal to logger console
        LoggingStream.stdout().messageWritten.connect(lambda msg: self.log_console.appendPlainText(msg))
        LoggingStream.stderr().messageWritten.connect(lambda msg: self.log_console.appendPlainText(msg))
        
        logging.info('Started "irrad_control" on %s' % platform.system())
        
    def _init_server(self):

        # SSH connection to server pi
        self.server = ServerManager(hostname=self.setup['tcp']['ip']['server'])

        # Worker that sets up the Raspberry Pi server by running installation script (install miniconda etc.)
        server_prep_worker = Worker(func=self.server.prepare_server)

        # Connect server preparation workers finished signal to launch server process
        for connection in [lambda: self.server.start_server_process(self.setup['tcp']['port']['cmd']),
                           lambda: self.send_cmd(target='server', cmd='start', cmd_data=self.setup)]:
            server_prep_worker.signals.finished.connect(connection)

        self.threadpool.start(server_prep_worker)
            
    def _init_threads(self):       
                
        # Fancy QThreadPool and QRunnable approach
        self.workers = {'recv_data': Worker(func=self.recv_data),
                        'recv_log': Worker(func=self.recv_log)}
        
        for worker in self.workers:
            self.threadpool.start(self.workers[worker])
            
    def _init_data_log(self):
        # Open log files for all adcs
        self.log_files = dict([(adc, open(self.setup['log']['file'].split('.')[0] + '_{}.txt'.format(adc), 'a'))
                               for adc in self.setup['daq']])

        for adc in self.log_files:    
            # write info header
            self.log_files[adc].write('# Date: %s \n' % time.asctime())
    
            # write data header
            d_header = '# Timestamp / s\t' + ' \t'.join('%s / V' % c for c in self.setup['daq'][adc]['channels']) + '\n'
            d_header += '# ch_types / s\t' + ' \t'.join('%s / V' % c for c in self.setup['daq'][adc]['types']) + '\n'
            
            self.log_files[adc].write(d_header)
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def update_tabs(self):

        current_tab = self.tabs.currentIndex()

        # Create missing tabs
        self.control_tab = QtWidgets.QWidget(parent=self.tabs)
        self.monitor_tab = IrradMonitor(daq_setup=self.setup['daq'], parent=self.tabs)

        # TODO: connections of control tab

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

            # TODO: Only log data when specified in control tab
            # if self.control_tab.log_data:
            self._log_data(data)

        # Check whether data is interpreted
        elif data['meta']['type'] == 'beam':
            self.daq_info_widget.update_beam_current(data)
            self.monitor_tab.plots[adc]['pos_plot'].set_data(data)
            _data = {'meta': data['meta'], 'data': data['data']['current']}
            self.monitor_tab.plots[adc]['current_plot'].set_data(_data)

        # Check whether data is interpreted
        elif data['meta']['type'] == 'fluence':
            self.monitor_tab.plots[adc]['fluence_plot'].set_data(data)
            
    def send_cmd(self, target, cmd, cmd_data=None):
        """Send a command *cmd* to a target *target* running within the server or interpreter process.
        The command can have respective data *cmd_data*. Targets must be listed in self.server_targets."""

        if target not in self.server_targets:
            msg = '{} not in known by command targets. Known targets: {}'.format(target, ', '.join(self.server_targets))
            logging.error(msg)
            return

        cmd_dict = {'target': target, 'cmd': cmd, 'data': cmd_data}
        cmd_worker = Worker(self._send_cmd_get_reply, cmd_dict)
        self.threadpool.start(cmd_worker)

    def _send_cmd_get_reply(self, cmd_dict):
        """Sending a command to the server and waiting for its reply. This runs on a separate QThread due
        to the blocking nature of the recv() method of sockets. *cmd_dict* contains the target, cmd and cmd_data."""

        # Spawn socket to send request to server and connect
        server_req = self.context.socket(zmq.REQ)
        server_req.connect(self._tcp_addr(self.setup['tcp']['port']['cmd'], self.setup['tcp']['ip']['server']))

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
        for ip in (self.setup['tcp']['ip']['server'], 'localhost'):
            data_sub.connect(self._tcp_addr(self.setup['tcp']['port']['data'], ip=ip))

        data_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        data_timestamps = {}
        
        logging.info('Data receiver ready')
        
        while self.receive_data:
            
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
        
        while self.receive_log:
            log = log_sub.recv()
            if log:
                self.log_received.emit(log.strip())

    def _log_data(self, data):
            
        timestamp = data['meta']['timestamp']
        _data = data['data']
        adc = data['meta']['name']
        
        if self.receive_data:
        
            # write timestamp to file
            self.log_files[adc].write('%f\t' % timestamp)
    
            # write voltages to file
            self.log_files[adc].write('\t'.join('%.{}f'.format(3) % _data[v] for v in self.setup['daq'][adc]['channels']) + '\n')

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
        # Stop receiver threads and delete
        self.receive_data = False
        self.receive_log = False
        self.threadpool.clear()
        
        # Close open log files
        for log_file in self.log_files:
            self.log_files[log_file].close()
            
        # Kill server process on host
        self.server.shutdown_server()

        if self.interpreter.is_alive():
            self.interpreter.terminate()
        
        # Give 1 second to shut everything down
        start = time.time()
        while time.time() - start < 1:
            QtWidgets.QApplication.processEvents()
        
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
