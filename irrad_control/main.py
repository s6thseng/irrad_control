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
from irrad_control.gui_widgets.daq_info_widget import DaqInfoWidget
from irrad_control.gui_widgets.plot_widgets import *
from irrad_control.gui_widgets.worker import Worker

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
    data_received = QtCore.pyqtSignal(dict)  # Signal for raw data
    data_rate = QtCore.pyqtSignal(str, float)  # Signal for incoming data rate
    update_raw_table = QtCore.pyqtSignal(dict)

    """
    Inits the main window of the irrad_control software.
    """
    def __init__(self, config_file, parent=None):
        super(IrradControlWin, self).__init__(parent)

        with open(config_file, 'r') as cf:
            self.config = yaml.safe_load(cf)

        self.config_file = config_file
        #self._init_server()
        self._init_ui()
        
        # Initiate worker objects and separate QThreads
        self.receive_data = True
        self.data_receiver_worker = Worker(func=self.recv_data)
        self.data_receiver_thread = QtCore.QThread()
        self.data_receiver_worker.moveToThread(self.data_receiver_thread)
        self.data_receiver_thread.started.connect(self.data_receiver_worker.work)
        self.data_receiver_thread.finished.connect(self.data_receiver_worker.deleteLater)
        self.data_receiver_thread.finished.connect(self.data_receiver_thread.deleteLater)
        self.data_receiver_thread.start()

        self.data_received.connect(lambda data: self.handle_data(data))

        #self.log_receiver_thread = QtCore.QThread()
        #self.data_interpreter_thread = QtCore.QThread()
        
        # start receiving data
        #log_thread = threading.Thread(target=self.log_data)
        #log_thread.start()
        
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

        self.sub_splitter.setSizes([int(0.5 * self.width()), int(0.5 * self.width())])
        self.main_splitter.setSizes([int(2. / 3. * self.height()), int(1. / 3. * self.height())])

        # Make dict to access tab widgets
        self.tw = {}

        # Init widgets and add to main windowScatterPlotItem
        self._init_menu()
        self._init_tabs()
        #self._init_logging()
        self._init_log_ui()
        self._init_raw_data_ui()

    def _init_tabs(self):
        """
        Initializes the tabs for the control window
        """

        # Add tab_widget and widgets for the different analysis steps
        self.tab_order = ('Setup', 'Control', 'Monitor')

        # Initialize each tab
        for name in self.tab_order:

            if name == 'Monitor':
                plw = pg.GraphicsLayoutWidget()#pg.PlotWidget(name=name)
                
                #self.p1 = plw.plot()
                #self.p1.setPen((200,200,100))
                #plw.setLabel('bottom', 'Horizontal position', units='V')
                #plw.setLabel('left', 'Vertical position', units='V')
                #plw.setXRange(-6, 6)
                #plw.setYRange(-6, 6)
                self.scatter_plot = pg.ScatterPlotItem()
                self.pos_v = pg.InfiniteLine(angle=0)
                self.pos_h = pg.InfiniteLine(angle=90)
                self.pos_h.setPen(color='w', style=QtCore.Qt.DashLine)
                self.pos_v.setPen(color='w', style=QtCore.Qt.DashLine)
                x = pg.InfiniteLine(angle=90, pos=0)
                y = pg.InfiniteLine(angle=0, pos=0)
                #plw.addItem(self.scatter_plot)
                #plw.addItem(self.pos_v)
                #plw.addItem(self.pos_h)
                #plw.addItem(x)
                #plw.addItem(y)
                plw.addItem(SEMCurrentGraph())
                plw.addItem((BeamCurrentGraph()))
                plw.addItem(BeamPositionGraph())
                plw.addItem(FluenceMap())
                self.tw[name] = plw
            else:
                self.tw[name] = QtWidgets.QWidget(parent=self.tabs)
                
            self.tabs.addTab(self.tw[name], name)
            
        #self.update_raw_table.connect(lambda data: self.handle_data(data))
        
    def _setup_server_communication(self):
        
        # open up ssh connection to server pi
        self.server = paramiko.SSHClient()
        self.server.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.server.connect(hostname=self.config['tcp']['ip']['server'], username='pi')

    def copy_to_server(self, local_file, remote_file):

        sftp = self.server.open_sftp()
        sftp.put(local_file, remote_file)
        sftp.close()
        
    def exec_server_cmd(self, cmd, bkg=False):
        
        # open up channel to exectute command through
        transport = self.server.get_transport()
        channel = transport.open_session()

        # add nohup and execute in background if specified
        _cmd = cmd if not bkg else 'nohup ' + cmd + ' &'
        
        # execute; this is non-blocking so we have to wait until cmd has been transmitted to server before closing
        channel.exec_command(cmd)
        
        while not channel.recv_ready():
            time.sleep(1)
        
        channel.close()
        
    def _init_server_process(self):
        
        # copy things to remote server
        self.copy_to_server(local_file='./irrad_config.yaml', remote_file='config_file.yaml')
        self.copy_to_server(local_file='../server/server_pi.py', remote_file='server_pi.py')
        
        # start server process
        self.exec_server_cmd(cmd='/home/pi/berryconda2/bin/python /home/pi/server_pi.py /home/pi/config_file.yaml',bkg=True)

    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)
    
    def handle_data(self, data):

        # Check whether data is interpreted
        if data['meta']['type'] == 'raw':
            self.daq_info_widget.update_data(data)
            
    def recv_data(self):
        
        context = zmq.Context()
        
        # data publisher
        data_sub = context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.config['tcp']['port']['raw_data'], ip=self.config['tcp']['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')

        data_timestamp = None
        
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

    def log_data(self):
        logfile = self.config['log']['file']
        context = zmq.Context()
        
        # data publisher
        data_sub = context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.config['tcp']['port']['data'], ip=self.config['tcp']['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')
        
        # open outfile
        self.log_out = open(logfile, 'a') 
            
        # write info header
        self.log_out.write('# Date: %s \n' % time.asctime())

        # write data header
        d_header = '# Timestamp / s\t' + ' \t'.join(
            '%s / V' % c for adc in self.config['daq'] for c in self.config[adc]['channels']) + '\n'
        d_header += '# ch_types / s\t' + ' \t'.join(
            '%s / V' % c for adc in self.config['daq'] for c in self.config[adc]['types']) + '\n'
        self.log_out.write(d_header)

        while True:
            
            meta_data = data_sub.recv_json()
            
            timestamp = meta_data['timestamp']
            data = meta_data['data']
            
            # write timestamp to file
            self.log_out.write('%f\t' % timestamp)

            # write voltages to file
            self.log_out.write('\t'.join('%.{}f'.format(3) % data[v] for v in self.config['adc_channels']) + '\n')

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
        self.appearance_menu.addAction('&Show/hide log', self.handle_log_UI, QtCore.Qt.CTRL + QtCore.Qt.Key_L)
        self.menuBar().addMenu(self.appearance_menu)

        self.help_menu = QtWidgets.QMenu('&Help', self)
        self.help_menu.addAction('&About', self.about)
        self.help_menu.addAction('&Documentation', self.open_docu)
        self.menuBar().addSeparator()
        self.menuBar().addMenu(self.help_menu)

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

    def _init_log_ui(self):
        """Initializes corresponding log widget"""

        # Widget to display log in, we only want to read log
        self.log_console = QtWidgets.QPlainTextEdit()
        self.log_console.setReadOnly(True)

        # Dock in which text widget is placed to make it closable without losing log content
        self.log_dock = QtWidgets.QDockWidget()
        self.log_dock.setWidget(self.log_console)
        self.log_dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.log_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable)
        self.log_dock.setWindowTitle('Log')

        # Set visibility to false at init
        self.log_dock.setVisible(False)

        # Add to main layout
        self.sub_splitter.addWidget(self.log_dock)

        logging.info('Started "irrad_control" on %s' % platform.system())

    def _init_raw_data_ui(self):
        """Initializes corresponding log widget"""

        # Make raw data widget
        self.daq_info_widget = DaqInfoWidget(self.config['daq'])
        #self.data_received.connect(lambda data: self.daq_info_widget.update_data(data))
        #self.data_rate.connect(lambda adc, drate: self.daq_info_widget.update_drate(adc, drate))

        # Dock in which text widget is placed to make it closable without losing log content
        self.raw_data_dock = QtWidgets.QDockWidget()
        self.raw_data_dock.setWidget(self.daq_info_widget)
        self.raw_data_dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea)
        self.raw_data_dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.raw_data_dock.setWindowTitle('DAQ Info')

        # Add to main layout
        self.sub_splitter.addWidget(self.raw_data_dock)

    def about(self):
        pass
        """QtWidgets.QMessageBox.about(self, "About",
                                    "Version\n%s.\n\n"
                                    "Authors\n%s\n\n"
                                    "GUI authors\n%s" % (irrad_control.VERSION,
                                                         AUTHORS.replace(', ', '\n'),
                                                         GUI_AUTHORS.replace(', ', '\n')))
        """
    def open_docu(self):
        pass
        #link = r'https://silab-bonn.github.io/testbeam_analysis/'
        #QtGui.QDesktopServices.openUrl(QtCore.QUrl(link))

    def handle_messages(self, message, ms=4000):
        """Handles messages from the tabs shown in QMainWindows statusBar"""

        self.statusBar().showMessage(message, ms)

    def handle_log_UI(self):
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

    def file_quit(self):
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