import yaml
import os
import time
import logging
import subprocess
from PyQt5 import QtWidgets, QtCore
from irrad_control import roe_output, ro_scales, ads1256
from irrad_control import proportionality_constants, server_ips, hardness_factors, config_path, daq_devices
from irrad_control.gui.widgets import ZmqSetupWindow
from irrad_control.utils import Worker, log_levels
from irrad_control.gui.widgets import GridContainer


def _fill_combobox_items(cbx, fill_dict):
    """Helper function to fill """

    default_idx = 0
    _all = fill_dict['all']

    # Add entire Info to tooltip e.g. date of measured constant, sigma, etc.
    for i, k in enumerate(sorted(_all.keys())):
        if 'hv_sem' in _all[k]:
            cbx.insertItem(i, '{} ({}, HV: {})'.format(_all[k]['nominal'], k, _all[k]['hv_sem']))
        else:
            cbx.insertItem(i, '{} ({})'.format(_all[k]['nominal'], k))
        tool_tip = ''
        for l in _all[k]:
            tool_tip += '{}: {}\n'.format(l, _all[k][l])
        cbx.model().item(i).setToolTip(tool_tip)

        default_idx = default_idx if k != fill_dict['default'] else i

    cbx.setCurrentIndex(default_idx)


def _get_host_ip():
    """Returns the host IP address on UNIX systems. If not UNIX, returns None"""

    try:
        host_ip = subprocess.check_output(['hostname', '-I'])
    except (OSError, subprocess.CalledProcessError):
        host_ip = None

    return host_ip


class IrradSetupTab(QtWidgets.QWidget):
    """Setup widget for the irradiation control software"""

    # Signal emitted when setup is completed
    setupCompleted = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super(IrradSetupTab, self).__init__(parent)

        # Layouts; split in half's
        self.main_layout = QtWidgets.QHBoxLayout()

        # Make two half's
        self.left_widget = QtWidgets.QTabWidget()
        self.left_widget.setLayout(QtWidgets.QVBoxLayout())
        self.right_widget = QtWidgets.QTabWidget()
        self.right_widget.setLayout(QtWidgets.QVBoxLayout())

        # Splitters
        self.main_splitter = QtWidgets.QSplitter()
        self.main_splitter.setOrientation(QtCore.Qt.Horizontal)
        self.main_splitter.addWidget(self.left_widget)
        self.main_splitter.addWidget(self.right_widget)
        self.main_splitter.setSizes([int(self.width() / 2.)] * 2)
        self.main_splitter.setChildrenCollapsible(False)
        self.right_widget.setMinimumSize(self.main_splitter.frameWidth(), self.main_splitter.height())

        # Add splitters to main layout
        self.main_layout.addWidget(self.main_splitter)

        # Add main layout to widget layout and add ok button
        self.setLayout(self.main_layout)

        # Dict to store info for setup in
        self.setup = {}
        self.server_setup = ServerSetupWidget()
        self.irrad_setup = IrradSetupWidget()
        self.irrad_setup.setup_widgets['selection'].serverSelection.connect(lambda selection: self.handle_server(selection))

        self.isSetup = False

        # Store widgets for daq and session input
        self.session_widgets = {}

        # Connect signal
        self.setupCompleted.connect(self.set_read_only)
        
        # Setup te widgets for daq, session and connect
        self._init_setup()

    def _init_setup(self):
        """Setup all the necesary widgets and connections"""

        # Left side first
        # Add main widget
        self.left_widget.layout().addWidget(self.irrad_setup)
        self.left_widget.layout().addStretch()

        # Button for completing the setup
        self.btn_ok = QtWidgets.QPushButton('Ok')
        self.btn_ok.clicked.connect(self.update_setup)
        self.btn_ok.clicked.connect(lambda: self.setupCompleted.emit(self.setup))
        self.btn_ok.clicked.connect(self._save_setup)
        self.btn_ok.setEnabled(False)

        self.left_widget.layout().addWidget(self.btn_ok)

        # Right side
        scroll_server = QtWidgets.QScrollArea()
        scroll_server.setWidgetResizable(True)
        scroll_server.setWidget(self.server_setup)
        # self.server_setup.setMinimumSize(800, 780)

        self.right_widget.layout().addWidget(QtWidgets.QLabel('Selected server(s)'))
        self.right_widget.layout().addWidget(scroll_server)

        # Connect
        self.irrad_setup.setupValid.connect(self._check_setup)
        self.server_setup.setupValid.connect(self._check_setup)

    def _check_setup(self):
        self.isSetup = self.irrad_setup.isSetup and self.server_setup.isSetup
        self.btn_ok.setEnabled(self.isSetup)

    def handle_server(self, selection):

        if selection['select']:
            self.server_setup.add_server(selection['ip'], name=selection['name'])
        else:
            self.server_setup.remove_server(selection['ip'])

    def _save_setup(self):
        """Save setup dict to yaml file and save in output path"""

        f = os.path.join(self.output_path, '{}_{}.yaml'.format(self.outfile, self.daq_widgets['name_combo'].currentText()))
        with open(f, 'w') as _setup:
            yaml.safe_dump(self.setup, _setup, default_flow_style=False)

    def update_setup(self):
        """Update the info into the setup dict"""

        # Update
        self.output_path = self.session_widgets['folder_edit'].text()
        self.outfile = self.session_widgets['outfile_edit'].text() or self.session_widgets['outfile_edit'].placeholderText()

        # Session setup
        self.setup['session'] = {}

        self.setup['session']['loglevel'] = self.session_widgets['logging_combo'].currentText()
        self.setup['session']['outfile'] = os.path.join(self.output_path, self.outfile)
        self.setup['session']['outfolder'] = self.output_path

        # DAQ setup
        self.setup['tcp'] = dict([('ip', {}), ('port', dict(self.zmq_setup.ports))])

        self.setup['tcp']['ip']['host'] = self.session_widgets['host_edit'].text()
        self.setup['tcp']['ip']['server'] = [self.session_widgets['server_edit'].text()]  # FIXME: hardcoded list

        # DAQ info
        self.setup['daq'] = {}

        # Make tmp dict to store later in setup dict
        tmp_daq = {}

        tmp_daq['channels'] = [ce.text() for ce in self.daq_widgets['channel_edits'] if ce.text()]

        tmp_daq['types'] = [tc.currentText() for i, tc in enumerate(self.daq_widgets['type_combos'])
                            if self.daq_widgets['channel_edits'][i].text()]

        tmp_daq['ch_numbers'] = [i if self.daq_widgets['ref_combos'][i].currentText() == 'GND' else (i, -1 + int(self.daq_widgets['ref_combos'][i].currentText())) for i, w in enumerate(self.daq_widgets['channel_edits']) if w.text()]

        tmp_daq['sampling_rate'] = int(self.daq_widgets['srate_combo'].currentText())

        tmp_daq['ro_scale'] = ro_scales[self.daq_widgets['scale_combo'].currentText()]

        tmp_daq['prop_constant'] = float(self.daq_widgets['prop_combo'].currentText().split()[0])

        tmp_daq['hardness_factor'] = float(self.daq_widgets['kappa_combo'].currentText().split()[0])

        self.setup['daq'][self.daq_widgets['name_combo'].currentText()] = tmp_daq

    def set_read_only(self, read_only=True):

        # Disable/enable main widgets to set to read_only
        self.left_widget.setEnabled(not read_only)
        self.right_widget.setEnabled(not read_only)
        self.btn_ok.setEnabled(not read_only)


class IrradSetupWidget(QtWidgets.QWidget):

    # Signal which is emitted whenever the server setup has been changed; bool indicates whether the setup is valid
    setupValid = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super(IrradSetupWidget, self).__init__(parent=parent)

        # The main layout for this widget
        self.setLayout(QtWidgets.QVBoxLayout())

        # Server setup; store the entire setup of all servers in this bad boy
        self.setup_widgets = {}

        # Store dict of ips and names
        self.server_ips = {}

        self.isSetup = False

        self._init_setup()

    def _init_setup(self):

        session_setup = SessionSetup('Session')
        network_setup = NetworkSetup('Network')
        server_selection = ServerSelection('Server selection')

        network_setup.serverIPsFound.connect(lambda ips: server_selection.add_selection(ips))
        network_setup.serverIPsFound.connect(
            lambda ips:
            server_selection.widgets[ips[0]].isChecked() if server_ips['default'] not in ips else server_selection.widgets[server_ips['default']].setChecked(1)
        )

        server_selection.serverSelection.connect(self._validate_setup)

        self.layout().addWidget(session_setup)
        self.layout().addWidget(network_setup)
        self.layout().addWidget(server_selection)

        self.setup_widgets['session'] = session_setup
        self.setup_widgets['network'] = network_setup
        self.setup_widgets['selection'] = server_selection

    def _validate_setup(self):

        try:

            if not any(chbx.isChecked() for chbx in self.setup_widgets['selection'].widgets.values()):
                self.isSetup = False
                return

            self.isSetup = True
        finally:
            self.setupValid.emit(self.isSetup)



class SessionSetup(GridContainer):

    def __init__(self, name, parent=None):
        super(SessionSetup, self).__init__(name=name, parent=parent)

        # Attributes for paths and files
        self.output_path = os.getcwd()
        self.outfile = None

        self._init_setup()

    def _init_setup(self):

        # Label and widgets to set the output folder
        label_folder = QtWidgets.QLabel('Output folder:')
        edit_folder = QtWidgets.QLineEdit()
        edit_folder.setText(self.output_path)
        edit_folder.setReadOnly(True)
        btn_folder = QtWidgets.QPushButton('Set folder')
        btn_folder.clicked.connect(self._get_output_folder)
        btn_folder.clicked.connect(lambda _: edit_folder.setText(self.output_path))

        # Add to layout
        self.add_widget(widget=[label_folder, edit_folder, btn_folder])

        # Label and widgets for output file
        label_out_file = QtWidgets.QLabel('Output file:')
        label_out_file.setToolTip('Name of output file containing raw and interpreted data')
        edit_out_file = QtWidgets.QLineEdit()
        edit_out_file.setPlaceholderText('irradiation_{}'.format('_'.join(time.asctime().split())))

        # Add to layout
        self.add_widget(widget=[label_out_file, edit_out_file])

        # Label and combobox to set logging level
        label_logging = QtWidgets.QLabel('Logging level:')
        combo_logging = QtWidgets.QComboBox()
        combo_logging.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        combo_logging.setCurrentIndex(1)

        # Add to layout
        self.add_widget(widget=[label_logging, combo_logging])

        self.widgets['logging_combo'] = combo_logging

    def _get_output_folder(self):
        """Opens a QFileDialog to select/create an output folder"""

        caption = 'Select output folder'
        path = QtWidgets.QFileDialog.getExistingDirectory(caption=caption, directory=self.output_path)

        # If a path has been selected and its not the current path, update
        if path and path != self.output_path:
            self.output_path = path


class NetworkSetup(GridContainer):

    serverIPsFound = QtCore.pyqtSignal(list)

    def __init__(self, name, parent=None):
        super(NetworkSetup, self).__init__(name=name, parent=parent)

        # Get global threadpool instance to launch search for available servers
        self.threadpool = QtCore.QThreadPool()
        self.available_servers = []
        self.selected_servers = []
        self.zmq_win = ZmqSetupWindow()

        self._init_setup()
        self.find_servers()

    def _init_setup(self):

        # Host PC IP label and widget
        label_host = QtWidgets.QLabel('Host IP:')
        edit_host = QtWidgets.QLineEdit()
        edit_host.setInputMask("000.000.000.000;_")
        host_ip = _get_host_ip()

        # If host can be found using _get_host_ip(), don't allow manual input and don't show
        if host_ip is not None:
            edit_host.setText(host_ip)
            edit_host.setReadOnly(True)
            label_host.setVisible(False)
            edit_host.setVisible(False)

        # Add to layout
        self.add_widget(widget=[label_host, edit_host])

        # Server IP label and widgets
        label_add_server = QtWidgets.QLabel('Add server IP:')
        edit_server = QtWidgets.QLineEdit()
        edit_server.setInputMask("000.000.000.000;_")
        edit_server.textEdited.connect(lambda text: btn_add_server.setEnabled(text not in server_ips['all']))
        edit_server.textEdited.connect(
            lambda text: btn_add_server.setToolTip(
                "IP already in list of known IPs" if text not in server_ips['all'] else "Add IP to list of known servers"))
        btn_add_server = QtWidgets.QPushButton('Add')
        btn_add_server.clicked.connect(lambda _: self._add_to_known_servers(ip=edit_server.text()))
        btn_add_server.clicked.connect(lambda _: self.find_servers())
        btn_add_server.clicked.connect(lambda _: btn_add_server.setEnabled(False))

        # Add to layout
        self.add_widget(widget=[label_add_server, edit_server, btn_add_server])

        # ZMQ related label and button; shows sub window for zmq setup since it generally doesn't need to be changed
        label_zmq = QtWidgets.QLabel('%sMQ setup' % u'\u00d8')
        btn_zmq = QtWidgets.QPushButton('Open %sMQ settings...' % u'\u00d8')
        btn_zmq.clicked.connect(lambda _: self.zmq_win.show())

        self.add_widget(widget=[label_zmq, btn_zmq])

        self.label_status = QtWidgets.QLabel("Status")
        self.serverIPsFound.connect(lambda ips: self.label_status.setText("{} of {} known servers found.".format(len(ips), len(server_ips['all']))))

        # Add to layout
        self.add_widget(widget=self.label_status)


        self.widgets['host_edit'] = edit_host

    def _add_to_known_servers(self, ip):
        """Add IP address *ip* to irrad_control.server_ips. Sets default IP if wanted"""

        msg = 'Set {} as default server address?'.format(ip)
        reply = QtWidgets.QMessageBox.question(self, 'Add server IP', msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            server_ips['default'] = ip

        server_ips['all'].append(ip)

        # Open the server_ips.yaml and overwrites it with current server_ips
        with open(os.path.join(config_path, 'server_ips.yaml'), 'w') as si:
            yaml.safe_dump(server_ips, si, default_flow_style=False)

    def find_servers(self):

        self.label_status.setText("Finding server(s)...")
        self.threadpool.start(Worker(func=self._find_available_servers))

    def _find_available_servers(self, timeout=10):

        n_available = len(server_ips['all'])
        start = time.time()
        while len(self.available_servers) != n_available and time.time() - start < timeout:

            for ip in server_ips['all']:
                # If we already have found this server in the network, continue
                if ip in self.available_servers:
                    continue

                p = subprocess.Popen(["ping", "-q", "-c 1", "-W 1", ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                res = p.communicate(), p.returncode
                if res[-1] == 0:
                    self.available_servers.append(ip)
                else:
                    n_available -= 1

        self.serverIPsFound.emit(self.available_servers)


class ServerSelection(GridContainer):

    serverSelection = QtCore.pyqtSignal(dict)

    def __init__(self, name, parent=None):
        super(ServerSelection, self).__init__(name=name, parent=parent)

    def add_selection(self, selection):

        for i, ip in enumerate(selection):

            if ip in self.widgets:
                continue

            chbx = QtWidgets.QCheckBox(str(ip))
            edit = QtWidgets.QLineEdit()
            edit.setPlaceholderText('Server {}'.format(i + 1))
            edit.placeholderText()

            # Connect
            chbx.stateChanged.connect(lambda state, e=edit, c=chbx: self.serverSelection.emit({'select': bool(state),
                                                                                               'ip': c.text(),
                                                                                               'name': e.placeholderText() if not e.text() else e.text()}))
            edit.textChanged.connect(lambda text, e=edit, c=chbx: self.serverSelection.emit({'select': c.isChecked(),
                                                                                             'ip': c.text(),
                                                                                             'name': e.placeholderText() if not text else text}) if c.isChecked() else e.setText(e.text()))

            self.widgets[ip] = chbx

            self.add_widget(widget=[chbx, edit])


class ServerSetupWidget(QtWidgets.QWidget):
    """
    Widget to do the setup of each available server. This includes what devices the server controls and
    the settings of these devices themselves. Each server is represented as tab within the self widget.
    """

    # Signal which is emitted whenever the server setup has been changed; bool indicates whether the setup is valid
    setupValid = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super(ServerSetupWidget, self).__init__(parent)

        # The main layout for this widget
        self.setLayout(QtWidgets.QVBoxLayout())

        # Tabs for each available server
        self.tabs = QtWidgets.QTabWidget()
        self.layout().addWidget(self.tabs)

        # Server setup; store the entire setup of all servers in this bad boy
        self.setup_widgets = {}
        self.tab_widgets = {}

        # Store dict of ips and names
        self.server_ips = {}

        self.isSetup = False

    def add_server(self, ip, name=None):
        """Add a server  with ip *ip* for setup"""

        # Number servers
        current_server = name if name is not None else 'Server {}'.format(self.tabs.count() + 1)

        # If this server is not already in setup
        if ip not in self.server_ips:
            # Store server name and ip
            self.server_ips[ip] = current_server

            # Setup
            self._init_setup(ip, current_server)
            self._connect_to_validation(ip)
            self._validate_setup()

        else:
            self.tabs.setTabText(self.tabs.indexOf(self.tab_widgets[ip]), current_server)

    def remove_server(self, ip):

        if ip not in self.tab_widgets:
            logging.warning("Sever {} not in setup and therefore cannot be removed.".format(ip))
            return

        self.tabs.removeTab(self.tabs.indexOf(self.tab_widgets[ip]))
        del self.tab_widgets[ip]
        del self.server_ips[ip]
        del self.setup_widgets[ip]

    def _init_setup(self, ip, name=None):

        # Layout
        _layout = QtWidgets.QVBoxLayout()

        # Init setup
        device_setup = DeviceSetup(name='Server devices')
        temp_setup = TempSetup(name='Temperature sensors')
        daq_setup = DAQSetup(name='DAQ (ADC)')
        adc_setup = ADCSetup(name='ADC')

        # Make connections

        # Device setup
        device_setup.widgets['adc'].stateChanged.connect(lambda state: adc_setup.setVisible(state))
        device_setup.widgets['adc'].stateChanged.connect(lambda state: daq_setup.setVisible(state))
        device_setup.widgets['temp'].stateChanged.connect(lambda state: temp_setup.setVisible(state))

        # If we are the first server, control stage
        device_setup.widgets['stage'].setChecked(len(self.server_ips) == 1)
        device_setup.widgets['adc'].setChecked(True)
        device_setup.widgets['temp'].setChecked(True)

        # Add to layout
        _layout.addWidget(device_setup)
        _layout.addWidget(temp_setup)
        _layout.addWidget(daq_setup)
        _layout.addWidget(adc_setup)
        _layout.addStretch()

        _widget = QtWidgets.QWidget()
        _widget.setLayout(_layout)

        # Store widgets
        self.setup_widgets[ip] = {'device': device_setup.widgets, 'temp': temp_setup.widgets, 'daq': daq_setup.widgets, 'adc': adc_setup.widgets}

        # Finally, add to tab bar
        self.tab_widgets[ip] = _widget
        self.tabs.addTab(_widget, name)

    def _validate_setup(self):
        """Check if all necessary input is ready to continue"""

        try:

            if len([ip for ip in self.server_ips if self.setup_widgets[ip]['device']['stage'].isChecked()]) > 1:
                logging.warning("Only one XY-Stage stage is currently supported.")
                self.isSetup = False
                return

            # Loop over all servers
            for ip in self.server_ips:

                # Check if server is used to control any device
                if not any(self.setup_widgets[ip]['device'][conf].isChecked() for conf in ('stage', 'adc', 'temp')):
                    logging.warning("No device selected for server {}. Please chose devices or remove server.".format(ip))
                    self.isSetup = False
                    return

                if self.setup_widgets[ip]['device']['temp'].isChecked() and not any(tcb.isChecked() for tcb in self.setup_widgets[ip]['temp']['temp_chbxs']):
                    logging.warning("Select temperature sensors for server {} or remove from devices.".format(ip))
                    self.isSetup = False
                    return

                if self.setup_widgets[ip]['device']['adc'].isChecked():

                    # Check text edits
                    edit_widgets = [self.setup_widgets[ip]['adc'][e] for e in self.setup_widgets[ip]['adc'] if 'edit' in e]

                    # Make func to check whether edit holds text
                    def _check(_edit):
                        t = _edit.text()
                        return True if t and t != '...' else False

                    # Loop over all widgets; if one has no text, stop
                    for edit in edit_widgets:
                        if isinstance(edit, list):
                            if not any(_check(e) for e in edit):
                                self.isSetup = False
                                return
                        else:
                            if not _check(edit):
                                self.isSetup = False
                                return

            self.isSetup = True

        finally:
            self.setupValid.emit(self.isSetup)

    def _connect_to_validation(self, ip):
        """Connect all input widgets to check the input each time an input is edited"""

        # Connect config widgets
        _ = [self.setup_widgets[ip]['device'][c].stateChanged.connect(self._validate_setup) for c in ('adc', 'temp', 'stage')]

        # Connect temp widgets
        _ = [chbx.stateChanged.connect(self._validate_setup) for chbx in self.setup_widgets[ip]['temp']['temp_chbxs']]

        # Loop over widgets
        for w in self.setup_widgets[ip]['adc']:
            # Check if it's an QLineEdit by key and connect its textEdited signal
            if 'edit' in w:
                if isinstance(self.setup_widgets[ip]['adc'][w], list):
                    for _w in self.setup_widgets[ip]['adc'][w]:
                        _w.textEdited.connect(self._validate_setup)
                else:
                    self.setup_widgets[ip]['adc'][w].textEdited.connect(self._validate_setup)


class DeviceSetup(GridContainer):

    def __init__(self, name, parent=None):
        super(DeviceSetup, self).__init__(name=name, parent=parent)

        self._init_setup()

    def _init_setup(self):

        checkbox_stage = QtWidgets.QCheckBox('XY-Stage')
        checkbox_adc = QtWidgets.QCheckBox('ADC')
        checkbox_temp = QtWidgets.QCheckBox('Temperature sensor')

        # Add to layout
        self.add_widget(widget=[checkbox_stage, checkbox_adc, checkbox_temp])

        self.widgets['adc'] = checkbox_adc
        self.widgets['stage'] = checkbox_stage
        self.widgets['temp'] = checkbox_temp


class TempSetup(GridContainer):

    def __init__(self, name, n_sensors=8, parent=None):
        super(TempSetup, self).__init__(name=name, parent=parent)

        self.n_sensors = n_sensors

        self._init_setup()

    def _init_setup(self):

        chbxs = []
        edits = []
        for i in range(self.n_sensors):
            chbx = QtWidgets.QCheckBox()
            edit = QtWidgets.QLineEdit()
            edit.setPlaceholderText('Sens. {}'.format(i + 1))
            chbx.stateChanged.connect(lambda state, e=edit: e.setEnabled(state))
            if i == 0:
                chbx.setChecked(True)
            chbx.stateChanged.emit(chbx.checkState())
            chbxs.append(chbx)
            edits.append(edit)

        # Add to layout
        widget_list = []
        widget_list1 = []
        for j in range(len(chbxs)):
            if j < int(len(chbxs)/2):
                widget_list.append(chbxs[j])
                widget_list.append(edits[j])
            else:
                widget_list1.append(chbxs[j])
                widget_list1.append(edits[j])

        self.add_widget(widget=widget_list)
        self.add_widget(widget=widget_list1)

        self.widgets['temp_chbxs'] = chbxs
        self.widgets['temp_edits'] = edits


class DAQSetup(GridContainer):
    
    def __init__(self, name, parent=None):
        super(DAQSetup, self).__init__(name=name, parent=parent)

        # Call setup
        self._init_setup()

    def _init_setup(self):

        # Label for name of DAQ device which is represented by the ADC
        label_sem = QtWidgets.QLabel('SEM name:')
        label_sem.setToolTip('Name of DAQ SEM e.g. SEM_C')
        combo_sem = QtWidgets.QComboBox()
        combo_sem.addItems(daq_devices['all'])
        combo_sem.setCurrentIndex(daq_devices['all'].index(daq_devices['default']))

        # Add to layout
        self.add_widget(widget=[label_sem, combo_sem])

        # Label for readout scale combobox
        label_kappa = QtWidgets.QLabel('Proton hardness factor %s:' % u'\u03ba')
        combo_kappa = QtWidgets.QComboBox()
        _fill_combobox_items(combo_kappa, hardness_factors)

        # Add to layout
        self.add_widget(widget=[label_kappa, combo_kappa])

        # Proportionality constant related widgets
        label_prop = QtWidgets.QLabel('Proportionality constant %s [1/V]:' % u'\u03bb')
        label_prop.setToolTip('Constant translating SEM signal to actual proton beam current via I_Beam = %s * I_FS * SEM_%s' % (u'\u03A3', u'\u03bb'))
        combo_prop = QtWidgets.QComboBox()
        _fill_combobox_items(combo_prop, proportionality_constants)

        # Add to layout
        self.add_widget(widget=[label_prop, combo_prop])

        # Store all daq related widgets in dict
        self.widgets['sem_combo'] = combo_sem
        self.widgets['kappa_combo'] = combo_kappa
        self.widgets['prop_combo'] = combo_prop


class ADCSetup(GridContainer):

    def __init__(self, name, n_channels=8, parent=None):
        super(ADCSetup, self).__init__(name=name, parent=parent)

        # ADC name / identifier
        self.n_channels = n_channels
        self.default_channels = ('Left', 'Right', 'Up', 'Down', 'Sum')

        # Call setup
        self._init_setup()

    def _init_setup(self):

        # Sampling rate related widgets
        label_sps = QtWidgets.QLabel('Sampling rate [sps]:')
        combo_srate = QtWidgets.QComboBox()
        combo_srate.addItems([str(drate) for drate in ads1256['drate'].values()])
        combo_srate.setCurrentIndex(ads1256['drate'].values().index(100))

        # Add to layout
        self.add_widget(widget=[label_sps, combo_srate])

        # Label for readout scale combobox
        label_scale = QtWidgets.QLabel('R/O electronics scale I_FS:')
        label_scale.setToolTip("Current corresponding to 5V full-scale voltage")
        combo_scale = QtWidgets.QComboBox()
        combo_scale.addItems(ro_scales.keys())
        combo_scale.setCurrentIndex(1)
        checkbox_scale = QtWidgets.QCheckBox('Set scale per channel')  # Allow individual scales per channel
        checkbox_scale.stateChanged.connect(lambda state: combo_scale.setEnabled(not bool(state)))

        # Add to layout
        self.add_widget(widget=[label_scale, combo_scale, checkbox_scale])

        # ADC channel related input widgets
        label_channel = QtWidgets.QLabel('Channels:')
        label_channel_number = QtWidgets.QLabel('#')
        label_channel_number.setToolTip('Number of the channel. Corresponds to physical channel on ADC')
        label_channel_name = QtWidgets.QLabel('Name')
        label_channel_name.setToolTip('Name of respective channel')
        label_channel_scale = QtWidgets.QLabel('R/O scale')
        label_channel_scale.setToolTip('Readout scale of respective channel')
        label_channel_type = QtWidgets.QLabel('Type')
        label_channel_type.setToolTip('Type of channel according to the custom readout electronics')
        label_channel_ref = QtWidgets.QLabel('Reference')
        label_channel_ref.setToolTip('Reference channel for measurement. Can be ground (GND) or any other channels.')

        # Add to layout
        self.add_widget(widget=label_channel)
        self.add_widget(widget=[label_channel_number, label_channel_name, label_channel_scale, label_channel_type, label_channel_ref])

        # Input widgets lists
        edits = []
        combos_types = []
        combos_refs = []
        combos_scales = []

        # Loop over number of available ADC channels which is 8.
        # Make combobox for channel type, edit for name and label for physical channel number
        for i in range(self.n_channels):

            # Channel RO scale combobox
            _cbx_scale = QtWidgets.QComboBox()
            _cbx_scale.addItems(ro_scales.keys())
            _cbx_scale.setToolTip('Select RO scale for each channel individually.')
            _cbx_scale.setCurrentIndex(combo_scale.currentIndex())

            # Channel type combobox
            _cbx_type = QtWidgets.QComboBox()
            _cbx_type.addItems(roe_output)
            _cbx_type.setToolTip('Select type of readout channel. If not None, this info is used for interpretation.')
            _cbx_type.setCurrentIndex(i if i < len(self.default_channels) else roe_output.index('none'))

            # Reference channel to measure voltage; can be GND or any of the other channels
            _cbx_ref = QtWidgets.QComboBox()
            _cbx_ref.addItems(['GND'] + [str(k) for k in range(1, self.n_channels + 1) if k != i + 1])
            _cbx_ref.setCurrentIndex(0)
            _cbx_ref.setProperty('lastitem', 'GND')
            _cbx_ref.currentTextChanged.connect(lambda item, c=_cbx_ref: self._handle_ref_channels(item, c))

            # Channel name edit
            _edit = QtWidgets.QLineEdit()
            _edit.setPlaceholderText('None')
            _edit.textChanged.connect(lambda text, cbx=_cbx_scale, checkbox=checkbox_scale: cbx.setEnabled(checkbox.isChecked() and (True if text else False)))
            _edit.textChanged.connect(lambda text, cbx=_cbx_type: cbx.setEnabled(True if text else False))
            _edit.textChanged.connect(lambda text, cbx=_cbx_ref: cbx.setEnabled(True if text else False))
            _edit.setText('' if i > len(self.default_channels) - 1 else self.default_channels[i])

            # Connections between RO scale combos
            checkbox_scale.stateChanged.connect(lambda state, cbx=_cbx_scale, edit=_edit: cbx.setEnabled(bool(state) if edit.text() else False))
            checkbox_scale.stateChanged.connect(lambda _, cbx=_cbx_scale, combo=combo_scale: cbx.setCurrentIndex(combo.currentIndex()))
            combo_scale.currentIndexChanged.connect(lambda idx, cbx=_cbx_scale, checkbox=checkbox_scale:
                                                    cbx.setCurrentIndex(idx if not checkbox.isChecked() else cbx.currentIndex()))

            # Disable widgets with no default channels at first
            _cbx_scale.setEnabled(False)
            _cbx_type.setEnabled(_edit.text() != '')
            _cbx_ref.setEnabled(_edit.text() != '')

            # Append to list
            edits.append(_edit)
            combos_types.append(_cbx_type)
            combos_refs.append(_cbx_ref)
            combos_scales.append(_cbx_scale)

            # Add to layout
            self.add_widget(widget=[QtWidgets.QLabel('{}.'.format(i + 1)), _edit, _cbx_scale, _cbx_type, _cbx_ref])

        # Store all input related widgets in dict
        self.widgets['scale_combo'] = combo_scale
        self.widgets['scale_combos'] = combos_scales
        self.widgets['type_combos'] = combos_types
        self.widgets['ref_combos'] = combos_refs
        self.widgets['channel_edits'] = edits
        self.widgets['srate_combo'] = combo_srate
        self.widgets['scale_chbx'] = checkbox_scale

    def _handle_ref_channels(self, item, cbx):
        """Handles the ADC channel selection"""
        
        sender_idx = self.widgets['ref_combos'].index(cbx) + 1

        idx = None if item == 'GND' else int(item) - 1
        lastitem = cbx.property('lastitem')
        last_idx = None if lastitem == 'GND' else int(lastitem)
        cbx.setProperty('lastitem', 'GND' if idx is None else str(idx))

        if idx:

            self.widgets['channel_edits'][idx].setText('')
            self.widgets['channel_edits'][idx].setPlaceholderText('Ref. to ch. {}'.format(sender_idx))
            self.widgets['channel_edits'][idx].setEnabled(False)

            for rcbx in self.widgets['ref_combos']:
                if cbx != rcbx:
                    for i in range(rcbx.count()):
                        if rcbx.itemText(i) == item or rcbx.itemText(i) == str(sender_idx):
                            rcbx.model().item(i).setEnabled(False)

        if last_idx:

            self.widgets['channel_edits'][last_idx].setEnabled(True)
            self.widgets['channel_edits'][last_idx].setPlaceholderText('None')

            for rcbx in self.widgets['ref_combos']:
                if cbx != rcbx:
                    for i in range(rcbx.count()):
                        if rcbx.itemText(i) == str(last_idx + 1) or (idx is None and rcbx.itemText(i) == str(sender_idx)):
                            rcbx.model().item(i).setEnabled(True)
