import yaml
import os
import time
import subprocess
from PyQt5 import QtWidgets, QtCore
from irrad_control import roe_output, ro_scales, ads1256
from irrad_control import proportionality_constants, server_ips, hardness_factors, config_path, daq_devices
from irrad_control.gui_widgets.sub_windows import ZmqSetupWindow


class IrradSetup(QtWidgets.QWidget):
    """Setup widget for the irradiation control software"""

    # Signal emitted when setup is completed
    setupCompleted = QtCore.pyqtSignal(dict)
    serverIPsFound = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super(IrradSetup, self).__init__(parent)

        # Set layout of this widget
        self.setLayout(QtWidgets.QVBoxLayout())

        # Dict to store info for setup in
        self.setup = {}

        # Make defaults
        self.default_channels = ('Left', 'Right', 'Up', 'Down', 'Sum')
        self.default_types = roe_output

        # Store widgets for daq and session input
        self.daq_widgets = {}
        self.session_widgets = {}
        
        # Number of channels per ADC (multiplexed)
        self.n_channels_per_adc = 8

        # Attributes for paths, files and ZMQ settings
        self.output_path = os.getcwd()
        self.outfile = None
        self.zmq_setup = ZmqSetupWindow(parent=self)

        # Layouts
        self.main_layout = QtWidgets.QHBoxLayout()
        self.left_layout = QtWidgets.QVBoxLayout()
        self.right_layout = QtWidgets.QVBoxLayout()

        # Add left and right to main
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.right_layout)

        # Button for completing the setup
        self.btn_ok = QtWidgets.QPushButton('Ok')
        self.btn_ok.clicked.connect(self.update_setup)
        self.btn_ok.clicked.connect(lambda: self.setupCompleted.emit(self.setup))
        self.btn_ok.clicked.connect(self._save_setup)

        # Connect signal
        self.setupCompleted.connect(self.set_read_only)
        
        # Add main layout to widget layout and add ok button
        self.layout().addLayout(self.main_layout)
        self.layout().addWidget(self.btn_ok)
        
        # Setup te widgets for daq, session and connect
        self._setup_session()
        self._setup_daq()
        self._connect_input_edits()
        self._check_input()

    def _setup_session(self):
        """Inits inputs related to the general irradiation session"""

        # Create left widget and layout
        self.left_widget = QtWidgets.QWidget()
        layout_session = QtWidgets.QGridLayout()
        layout_session.setHorizontalSpacing(20)
        layout_session.setVerticalSpacing(10)
        layout_session.setAlignment(QtCore.Qt.AlignTop)
        self.left_widget.setLayout(layout_session)

        # Label for session
        label_session = QtWidgets.QLabel('Irradiation session')
        layout_session.addWidget(label_session, 0, 0, 1, 3)

        # Label and widgets to set the output folder
        label_folder = QtWidgets.QLabel('Output folder:')
        edit_folder = QtWidgets.QLineEdit()
        edit_folder.setText(self.output_path)
        edit_folder.setReadOnly(True)
        btn_folder = QtWidgets.QPushButton('Set folder')
        btn_folder.clicked.connect(self._get_output_folder)
        btn_folder.clicked.connect(lambda _: edit_folder.setText(self.output_path))

        # Add to layout
        layout_session.addWidget(label_folder, 1, 1, 1, 1)
        layout_session.addWidget(edit_folder, 1, 2, 1, 1)
        layout_session.addWidget(btn_folder, 1, 3, 1, 1)

        # Label and widgets for output file
        label_out_file = QtWidgets.QLabel('Output file:')
        label_out_file.setToolTip('Name of output file containing raw and interpreted data')
        edit_out_file = QtWidgets.QLineEdit()
        edit_out_file.setPlaceholderText('irradiation_{}'.format('_'.join(time.asctime().split())))

        # Add to layout
        layout_session.addWidget(label_out_file, 2, 1, 1, 1)
        layout_session.addWidget(edit_out_file, 2, 2, 1, 1)

        # Label and combobox to set logging level
        label_logging = QtWidgets.QLabel('Logging level:')
        combo_logging = QtWidgets.QComboBox()
        combo_logging.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        combo_logging.setCurrentIndex(1)

        # Add to layout
        layout_session.addWidget(label_logging, 3, 1, 1, 1)
        layout_session.addWidget(combo_logging, 3, 2, 1, 1)

        # Label for network settings
        label_network = QtWidgets.QLabel('Network settings')
        layout_session.addWidget(label_network, 4, 0, 1, 3)

        # Server IP label and widgets
        label_server = QtWidgets.QLabel('Server IP:')
        edit_server = QtWidgets.QLineEdit()
        edit_server.setInputMask("000.000.000.000;_")
        edit_server.textEdited.connect(lambda text: btn_add_server.setEnabled(text not in server_ips['all']))
        combo_server = QtWidgets.QComboBox()
        combo_server.currentTextChanged.connect(lambda text: btn_add_server.setEnabled(text not in server_ips['all']))
        combo_server.setLineEdit(edit_server)

        # Connect server ip edit to signals; on startup, servers are searched for automatically
        for x in [lambda ip_list, cbx=combo_server: cbx.addItems(ip_list),
                  lambda ip_list, edt=edit_server, cbx=combo_server: edt.setText(server_ips['default']
                                                                                 if server_ips['default'] in ip_list
                                                                                 else cbx.itemText(0)),
                  self._check_input]:
            self.serverIPsFound.connect(x)

        btn_add_server = QtWidgets.QPushButton('Add')
        btn_add_server.setToolTip('Add current IP to list of known servers.')
        btn_add_server.clicked.connect(lambda _: self._add_to_known_servers(ip=edit_server.text()))
        btn_add_server.clicked.connect(lambda _: combo_server.addItem(edit_server.text()))
        btn_add_server.setEnabled(False)

        # Add to layout
        layout_session.addWidget(label_server, 5, 1, 1, 1)
        layout_session.addWidget(combo_server, 5, 2, 1, 1)
        layout_session.addWidget(btn_add_server, 5, 3, 1, 1)

        # Host PC IP label and widget
        label_host = QtWidgets.QLabel('Host IP:')
        edit_host = QtWidgets.QLineEdit()
        edit_host.setInputMask("000.000.000.000;_")
        host_ip = self._get_host_ip()

        # If host can be found using self._get_host_ip(), don't allow manual input
        if host_ip is not None:
            edit_host.setText(host_ip)
            edit_host.setReadOnly(True)

        # Add to layout
        layout_session.addWidget(label_host, 6, 1, 1, 1)
        layout_session.addWidget(edit_host, 6, 2, 1, 1)

        # ZMQ related label and button; shows sub window for zmq setup since it generally doesn't need to be changed
        label_zmq = QtWidgets.QLabel('%sMQ setup' % u'\u00d8')
        btn_zmq = QtWidgets.QPushButton('Open %sMQ settings...' % u'\u00d8')
        btn_zmq.clicked.connect(lambda _: self.zmq_setup.show())

        # Add to layout
        layout_session.addWidget(label_zmq, 7, 1, 1, 1)
        layout_session.addWidget(btn_zmq, 7, 2, 1, 1)

        # Store all relevant input widgets
        self.session_widgets['folder_edit'] = edit_folder
        self.session_widgets['outfile_edit'] = edit_out_file
        self.session_widgets['logging_combo'] = combo_logging
        self.session_widgets['server_edit'] = edit_server
        self.session_widgets['host_edit'] = edit_host

        # Add to left layout
        self.left_layout.addWidget(self.left_widget)

    def _setup_daq(self):
        """Inits inputs related to the setup of the data acquisition ADC"""

        # Create right widget and layout
        self.right_widget = QtWidgets.QWidget()
        layout_daq = QtWidgets.QGridLayout()
        layout_daq.setVerticalSpacing(10)
        layout_daq.setHorizontalSpacing(20)
        layout_daq.setAlignment(QtCore.Qt.AlignTop)
        self.right_widget.setLayout(layout_daq)

        # Input widgets lists
        edits = []
        combos_types = []
        combos_refs = []

        # Label for DAQ device
        label_daq = QtWidgets.QLabel('DAQ')
        layout_daq.addWidget(label_daq, 0, 0, 1, 3)

        # Label for name of DQA device which is represented by the ADC
        label_name = QtWidgets.QLabel('Device name:')
        label_name.setToolTip('Name of DAQ device e.g. SEM_C')
        combo_name = QtWidgets.QComboBox()
        combo_name.addItems(daq_devices['all'])
        combo_name.setCurrentIndex(daq_devices['all'].index(daq_devices['default']))

        # Add to layout
        layout_daq.addWidget(label_name, 1, 1, 1, 1)
        layout_daq.addWidget(combo_name, 1, 2, 1, 3)

        # Label for readout scale combobox
        label_kappa = QtWidgets.QLabel('Proton hardness factor %s:' % u'\u03ba')
        combo_kappa = QtWidgets.QComboBox()
        self._fill_combobox_items(combo_kappa, hardness_factors)

        # Add to layout
        layout_daq.addWidget(label_kappa, 2, 1, 1, 1)
        layout_daq.addWidget(combo_kappa, 2, 2, 1, 3)

        # Label for readout scale combobox
        label_scale = QtWidgets.QLabel('RO electronics 5V full-scale:')
        combo_scale = QtWidgets.QComboBox()
        combo_scale.addItems(ro_scales.keys())
        combo_scale.setCurrentIndex(1)

        # Add to layout
        layout_daq.addWidget(label_scale, 3, 1, 1, 1)
        layout_daq.addWidget(combo_scale, 3, 2, 1, 3)

        # Proportionality constant related widgets
        label_prop = QtWidgets.QLabel('Proportionality constant %s [1/V]:' % u'\u03bb')
        label_prop.setToolTip('Constant translating SEM signal to actual proton beam current via I_Beam = %s * RO_scale * SEM_sig' % u'\u03bb')
        combo_prop = QtWidgets.QComboBox()
        self._fill_combobox_items(combo_prop, proportionality_constants)

        # Add to layout
        layout_daq.addWidget(label_prop, 4, 1, 1, 1)
        layout_daq.addWidget(combo_prop, 4, 2, 1, 3)

        # Sampling rate related widgets
        label_srate = QtWidgets.QLabel('Sampling rate [sps]:')
        combo_srate = QtWidgets.QComboBox()
        combo_srate.addItems([str(drate) for drate in ads1256['drate'].values()])
        combo_srate.setCurrentIndex(ads1256['drate'].values().index(100))

        # Add to layout
        layout_daq.addWidget(label_srate, 5, 1, 1, 1)
        layout_daq.addWidget(combo_srate, 5, 2, 1, 3)

        # ADC channel related input widgets
        label_channel = QtWidgets.QLabel('ADC channels:')
        label_channel_number = QtWidgets.QLabel('#')
        label_channel_number.setToolTip('Number of the channel. Corresponds to physical channel on ADC')
        label_channel_name = QtWidgets.QLabel('Name')
        label_channel_name.setToolTip('Name of respective channel')
        label_type = QtWidgets.QLabel('Type')
        label_type.setToolTip('Type of channel according to the custom readout electronics')
        label_ref = QtWidgets.QLabel('Reference')
        label_ref.setToolTip('Reference channel for voltage measurement. Can be ground (GND) or any of the other channels')

        # Add to layout
        layout_daq.addWidget(label_channel, 6, 1, 1, 1)
        layout_daq.addWidget(label_channel_number, 6, 2, 1, 1)
        layout_daq.addWidget(label_channel_name, 6, 3, 1, 1)
        layout_daq.addWidget(label_type, 6, 4, 1, 1)
        layout_daq.addWidget(label_ref, 6, 5, 1, 1)

        # Loop over number of available ADC channels which is 8.
        # Make combobox for channel type, edit for name and label for physical channel number
        for i in range(self.n_channels_per_adc):
            # Channel type combobox
            _cbx_type = QtWidgets.QComboBox()
            _cbx_type.addItems(self.default_types)
            _cbx_type.setToolTip('Select type of readout channel. If not None, this info is used for data analysis and visualization.')
            _cbx_type.setCurrentIndex(i if i < len(self.default_channels) else self.default_types.index('none'))

            # Reference channel to measure voltage; can be GND or any of the other channels
            _cbx_ref = QtWidgets.QComboBox()
            _cbx_ref.addItems(['GND'] + [str(k) for k in range(1, self.n_channels_per_adc + 1) if k != i + 1])
            _cbx_ref.setCurrentIndex(0)
            _cbx_ref.setProperty('lastitem', 'GND')
            _cbx_ref.currentTextChanged.connect(lambda item, c=_cbx_ref: self._handle_ref_channels(item, c))

            # Channel name edit
            _edit = QtWidgets.QLineEdit()
            _edit.setPlaceholderText('None')
            _edit.textChanged.connect(lambda text, cbx=_cbx_type: cbx.setEnabled(True if text else False))
            _edit.textChanged.connect(lambda text, cbx=_cbx_ref: cbx.setEnabled(True if text else False))
            _edit.setText('' if i > len(self.default_channels) - 1 else self.default_channels[i])

            # Disable widgets with no default channels at first
            _cbx_type.setEnabled(_edit.text() != '')
            _cbx_ref.setEnabled(_edit.text() != '')

            # Append to list
            edits.append(_edit)
            combos_types.append(_cbx_type)
            combos_refs.append(_cbx_ref)

            # Add to layout
            layout_daq.addWidget(QtWidgets.QLabel('{}.'.format(i+1)), i + 7, 2, 1, 1)
            layout_daq.addWidget(_edit, i + 7, 3, 1, 1)
            layout_daq.addWidget(_cbx_type, i + 7, 4, 1, 1)
            layout_daq.addWidget(_cbx_ref, i + 7, 5, 1, 1)

        # Store all input related widgets in dict
        self.daq_widgets['name_combo'] = combo_name
        self.daq_widgets['kappa_combo'] = combo_kappa
        self.daq_widgets['prop_combo'] = combo_prop
        self.daq_widgets['scale_combo'] = combo_scale
        self.daq_widgets['srate_combo'] = combo_srate
        self.daq_widgets['channel_edits'] = edits
        self.daq_widgets['type_combos'] = combos_types
        self.daq_widgets['ref_combos'] = combos_refs

        # Add this widget to right widget
        self.right_layout.addWidget(self.right_widget)

    def _handle_ref_channels(self, item, cbx):

        sender_idx = self.daq_widgets['ref_combos'].index(cbx) + 1

        idx = None if item == 'GND' else int(item) - 1
        lastitem = cbx.property('lastitem')
        last_idx = None if lastitem == 'GND' else int(lastitem)
        cbx.setProperty('lastitem', 'GND' if idx is None else str(idx))

        if idx:

            self.daq_widgets['channel_edits'][idx].setText('')
            self.daq_widgets['channel_edits'][idx].setPlaceholderText('Ref. to ch. {}'.format(sender_idx))
            self.daq_widgets['channel_edits'][idx].setEnabled(False)

            for rcbx in self.daq_widgets['ref_combos']:
                if cbx != rcbx:
                    for i in range(rcbx.count()):
                        if rcbx.itemText(i) == item or rcbx.itemText(i) == str(sender_idx):
                            rcbx.model().item(i).setEnabled(False)

        if last_idx:

            self.daq_widgets['channel_edits'][last_idx].setEnabled(True)
            self.daq_widgets['channel_edits'][last_idx].setPlaceholderText('None')

            for rcbx in self.daq_widgets['ref_combos']:
                if cbx != rcbx:
                    for i in range(rcbx.count()):
                        if rcbx.itemText(i) == str(last_idx + 1) or (idx is None and rcbx.itemText(i) == str(sender_idx)):
                            rcbx.model().item(i).setEnabled(True)

    def _fill_combobox_items(self, cbx, fill_dict):

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

    def _check_input(self):
        """Check if all necessary input is ready to continue"""

        # Flag to check
        all_set = True

        # Get all input widgets
        edit_widgets = [se[ew] for se in (self.daq_widgets, self.session_widgets) for ew in se if 'edit' in ew]

        # Make func to check whether edit holds text
        def _check(_edit):
            t = _edit.text() or _edit.placeholderText()
            return True if t and t != '...' else False

        # Loop over all widgets; if one has no text, stop
        i = 0
        while all_set and i < len(edit_widgets):
            edit = edit_widgets[i]
            if isinstance(edit, list):
                if not any(_check(e) for e in edit):
                    all_set = False
            else:
                all_set = _check(edit)

            i += 1

        # Set ok button accordingly
        self.btn_ok.setEnabled(all_set)

    def _connect_input_edits(self):
        """Connect all input widgets to check the input each time an input is edited"""

        # Loop over widgets
        for setup_widget in (self.daq_widgets, self.session_widgets):
            for widget in setup_widget:
                # Check if it's an QLineEdit by key and connect its textEdited signal
                if 'edit' in widget:
                    if isinstance(setup_widget[widget], list):
                        for w in setup_widget[widget]:
                            w.textEdited.connect(self._check_input)
                    else:
                        setup_widget[widget].textEdited.connect(self._check_input)

    def _get_output_folder(self):
        """Opens a QFileDialog to select/create an output folder"""

        caption = 'Select output folder'
        path = QtWidgets.QFileDialog.getExistingDirectory(caption=caption, directory=self.output_path)

        # If a path has been selected and its not the current path, update
        if path and path != self.output_path:
            self.output_path = path

    def _add_to_known_servers(self, ip):
        """Add IP address *ip* to irrad_control.server_ips. Sets default IP if wanted"""

        msg = 'Set {} as default server address?'.format(ip)
        reply = QtWidgets.QMessageBox.question(self, 'Add server IP', msg, QtWidgets.QMessageBox.Yes,
                                               QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            server_ips['default'] = ip

        server_ips['all'].append(ip)

        # Open the server_ips.yaml and overwrites it with current server_ips
        with open(os.path.join(config_path, 'server_ips.yaml'), 'w') as si:
            yaml.safe_dump(server_ips, si, default_flow_style=False)

    def _get_host_ip(self):
        """Returns the host IP address on UNIX systems. If not UNIX, returns None"""

        try:
            host_ip = subprocess.check_output(['hostname', '-I'])
        except (OSError, subprocess.CalledProcessError):
            host_ip = None

        return host_ip

    def _find_available_servers(self, timeout=60):

        available = []
        start = time.time()
        while not available and time.time() - start < timeout:
            for ip in server_ips['all']:
                p = subprocess.Popen(["ping", "-q", "-c 1", "-W 1", ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                res = p.communicate(), p.returncode
                if res[-1] == 0:
                    available.append(ip)

        self.serverIPsFound.emit(available)

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
        self.setup['tcp']['ip']['server'] = self.session_widgets['server_edit'].text()

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
