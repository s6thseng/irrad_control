import sys
import time
import logging
import platform
import zmq
import yaml
import argparse
import paramiko
from collections import OrderedDict
from email import message_from_string
from pkg_resources import get_distribution, DistributionNotFound
from PyQt5 import QtCore, QtWidgets, QtGui
from irrad_control.utils.logger import IrradLogger, LoggingStream
from irrad_control.utils.worker import Worker
from irrad_control.utils.server_manager import ServerManager
from irrad_control.gui_widgets.daq_info_widget import DaqInfoWidget
from irrad_control.gui_widgets.plot_widgets import PlotWrapperWidget, RawDataPlot,BeamPositionPlot


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

    # PyQt signals
    data_received = QtCore.pyqtSignal(dict)  # Signal for data
    reply_received = QtCore.pyqtSignal(str)  # Signal for data
    log_received = QtCore.pyqtSignal(str)

    """
    Inits the main window of the irrad_control software.
    """
    def __init__(self, config_file, parent=None):
        super(IrradControlWin, self).__init__(parent)

        with open(config_file, 'r') as cf:
            self.config = yaml.safe_load(cf)

        self.config_file = config_file
        
        # Needed in ordeer to stop helper threads
        self.receive_data = True
        self.receive_log = True
        self.receive_reply = True
        
        # ZMQ context; THIS IS THREADSAFE! SOCKETS ARE NOT! EACH SOCKET NEEDS TO BE CREATED WITHIN ITS RESPECTIVE THREAD/PROCESS!
        self.context = zmq.Context()
        self.server_req = self.context.socket(zmq.REQ)
        
        # QThreadPool manages GUI threads on its own
        self.threadpool = QtCore.QThreadPool()
        
        self.data_received.connect(lambda data: self.handle_data(data))
        self.reply_received.connect(lambda reply: self.handle_reply(reply))
        self.log_received.connect(lambda log: logging.info(log))
        
        self._init_ui()
        self._init_logging()
        self._init_server()
        self._init_threads()
        
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

        # Make dict to access tab widgets
        self.tw = {}

        # Init widgets and add to main windowScatterPlotItem
        self._init_menu()
        self._init_tabs()
        self._init_docks()
        
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

        # Initialize each tab
        for name in self.tab_order:
            #if name == 'Setup':
                #self.tw[name] = QtWidgets.QPushButton('Send config')
                #self.tw[name].clicked.connect(lambda: self.server_req.send_json({'cmd': 'setup_server', 'data': self.config}))
            if name == 'Monitor':
                widget = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout()
                widget.setLayout(layout)
                
                self.raw_plot = RawDataPlot(self.config['daq']['SEM_C'])
                self.pos_plot = BeamPositionPlot(self.config['daq']['SEM_C'])
                
                raw_widget = PlotWrapperWidget(self.raw_plot)
                pos_widget = PlotWrapperWidget(self.pos_plot)
                
                layout.addWidget(raw_widget)
                layout.addWidget(pos_widget)
                
                self.tw[name] = widget
                
            else:
                self.tw[name] = QtWidgets.QWidget()
            self.tabs.addTab(self.tw[name], name)
            
    def _init_docks(self):
        """Initializes corresponding log and daq info dock"""

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

        # Make raw data widget
        self.daq_info_widget = DaqInfoWidget(self.config['daq'])

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
        
        if 'fake_data' not in self.config:
        
            self.server = ServerManager(hostname=self.config['tcp']['ip']['server'])
            prep_worker = Worker(func=self.server.prepare_server)
            prep_worker.signals.finished.connect(lambda: self.server.start_server_process(self.config['tcp']['port']['server']))
            prep_worker.signals.finished.connect(self.server_req.connect(self._tcp_addr(self.config['tcp']['port']['server'],
                                                                                        self.config['tcp']['ip']['server'])))
            
            self.threadpool.start(prep_worker)
            
    def _init_threads(self):       
                
        # Fancy QThreadPool and QRunnable approach
        self.workers = {'recv_data': Worker(func=self.recv_data),
                        'recv_log': Worker(func=self.recv_log)}
        
        for worker in self.workers:
            self.threadpool.start(self.workers[worker])
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)
    
    def handle_data(self, data):

        # Check whether data is interpreted
        if data['meta']['type'] == 'raw':
            self.daq_info_widget.update_data(data)
            self.raw_plot.set_data(data)
            self.pos_plot.set_data(data)
            
    def handle_reply(self, reply):
        print reply
            
    def recv_data(self):
        
        # Data subscriber
        data_sub = self.context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.config['tcp']['port']['raw_data'], 'localhost'))#self.config['tcp']['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        data_timestamp = None
        
        logging.info('Data receiver ready')
        
        while self.receive_data:
            
            data = data_sub.recv_json()

            if data_timestamp is None:
                data_timestamp = time.time()
            else:
                if data['meta']['type'] == 'raw':
                    now = time.time()
                    drate = 1. / (now - data_timestamp)
                    data_timestamp = now
                    data['meta']['data_rate'] = drate

            self.data_received.emit(data)
            
    def recv_log(self):
        
        # Log subscriber
        log_sub = self.context.socket(zmq.SUB)
        log_sub.connect(self._tcp_addr(self.config['tcp']['port']['log'], ip=self.config['tcp']['ip']['server']))
        log_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        logging.info('Log receiver ready')
        
        while self.receive_log:
            log = log_sub.recv()
            if log:
                self.log_received.emit(log)

    def _log_data(self, data):
        
        logfile = self.config['log']['file']
        
        # open outfile(s)
        self.log_files = dict([(adc, open(logfile.split('.')[0] + '_{}.txt'.format(adc), 'a')) for adc in self.config['daq']])
        
        for adc in self.log_files:    
            # write info header
            self.log_files[adc].write('# Date: %s \n' % time.asctime())
    
            # write data header
            d_header = '# Timestamp / s\t' + ' \t'.join('%s / V' % c for c in self.config['daq'][adc]['channels']) + '\n'
            d_header += '# ch_types / s\t' + ' \t'.join('%s / V' % c for c in self.config['daq'][adc]['types']) + '\n'
            
            self.log_files[adc].write(d_header)
        
        logging.info('Log data receiver ready')
        
        while self.receive_data:
            
            meta_data = data_sub.recv_json()
            
            timestamp = meta_data['timestamp']
            data = meta_data['data']
            adc = meta_data['name']
            
            # write timestamp to file
            self.log_files[adc].write('%f\t' % timestamp)

            # write voltages to file
            self.log_files[adc].write('\t'.join('%.{}f'.format(3) % data[v] for v in self.config['daq'][adc]['channels']) + '\n')
        
        for log_file in self.log_files:
            log_file.close()

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
        self.receive_data = False
        self.receive_log = False
        self.receive_reply = False
        self.threadpool.clear()
        
    def file_quit(self):
        self._clean_up()
        self.close()

    def closeEvent(self, _):
        self.file_quit()
        

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', nargs='?', help='Configuration yaml file', default=None)
    args_parsed = parser.parse_args(sys.argv[1:])
    if not args_parsed.config_file:
        parser.error("You have to specify a configuration file")  # pragma: no cover, sysexit
    
    app = QtWidgets.QApplication(sys.argv)
    font = QtGui.QFont()
    font.setPointSize(11)
    app.setFont(font)
    icw = IrradControlWin(args_parsed.config_file)
    icw.show()
    icw.check_resolution()
    sys.exit(app.exec_())