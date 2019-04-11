from PyQt5 import QtWidgets, QtCore, QtGui


class IrradControl(QtWidgets.QWidget):
    """Control widget for the irradiation control software"""

    sendStageCmd = QtCore.pyqtSignal(dict)
    scanPrepared = QtCore.pyqtSignal(dict)

    def __init__(self, irrad_setup, parent=None):
        super(IrradControl, self).__init__(parent)

        # Layouts; split in quadrants
        self.main_layout = QtWidgets.QHBoxLayout()

        # Make quadrants
        self.info_widget = QtWidgets.QWidget()
        self.info_widget.setLayout(QtWidgets.QVBoxLayout())
        self.control_widget = QtWidgets.QWidget()
        self.control_widget.setLayout(QtWidgets.QVBoxLayout())
        self.scan_widget = QtWidgets.QWidget()
        self.scan_widget.setLayout(QtWidgets.QVBoxLayout())
        self.after_widget = QtWidgets.QWidget()
        self.after_widget.setLayout(QtWidgets.QVBoxLayout())

        # Splitters
        self.main_splitter = QtWidgets.QSplitter()
        self.main_splitter.setOrientation(QtCore.Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.sub_splitter_1 = QtWidgets.QSplitter()
        self.sub_splitter_1.setOrientation(QtCore.Qt.Horizontal)
        self.sub_splitter_1.setChildrenCollapsible(False)
        self.sub_splitter_1.addWidget(self.control_widget)
        self.sub_splitter_1.addWidget(self.scan_widget)
        self.sub_splitter_1.setSizes([int(self.width() / 2.)] * 2)
        self.sub_splitter_2 = QtWidgets.QSplitter()
        self.sub_splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.sub_splitter_2.setChildrenCollapsible(False)
        self.sub_splitter_2.addWidget(self.after_widget)
        self.sub_splitter_2.addWidget(self.info_widget)
        self.sub_splitter_2.setSizes([int(self.width() / 2.)] * 2)
        self.main_splitter.addWidget(self.sub_splitter_1)
        self.main_splitter.addWidget(self.sub_splitter_2)
        self.main_splitter.setSizes([int(self.height() / 2.)] * 2)

        # Add splitters to main layout
        self.main_layout.addWidget(self.main_splitter)
        
        # Add main layout to widget layout and add ok button
        self.setLayout(self.main_layout)

        # General attributes
        self.setup = irrad_setup

        # Attributes for the stage
        self.current_pos = [0.0, 0.0]
        self.current_speed = [0.0, 0.0]
        self.scan_speed = None
        self.step_size = None
        self.n_rows = None

        # Setup the widgets for each quadrant
        self._setup_control()
        self._setup_scan()
        self._setup_after()
        self._setup_info()

        # Send command to find where stage is and what the speeds are
        self.send_stage_cmd('pos')
        self.send_stage_cmd('get_speed')

    def _setup_control(self):

        # Label for setup control layout
        label_setup = QtWidgets.QLabel('Setup control')
        self.control_widget.layout().addWidget(label_setup, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

        # Grid layout to group widgets
        layout_setup = QtWidgets.QGridLayout()

        label_stage = QtWidgets.QLabel('XY-Stage:')

        # Button to home the device
        label_home = QtWidgets.QLabel('Home stage:')
        btn_home = QtWidgets.QPushButton('Home axes')
        btn_home.clicked.connect(lambda _: self.send_stage_cmd('home'))

        # Movement speed
        label_speed = QtWidgets.QLabel('Set speed:')
        spx_speed = QtWidgets.QDoubleSpinBox()
        spx_speed.setMinimum(0.000303)
        spx_speed.setMaximum(205.)
        spx_speed.setDecimals(3)
        spx_speed.setSuffix(' mm/s')
        cbx_axis = QtWidgets.QComboBox()
        cbx_axis.addItems(['x', 'y'])
        btn_set_speed = QtWidgets.QPushButton('Set speed')
        btn_set_speed.clicked.connect(lambda _: self.send_stage_cmd('set_speed', cmd_data={'axis': cbx_axis.currentText(),
                                                                                           'speed': spx_speed.value(),
                                                                                           'unit': 'mm/s'}))
        btn_set_speed.clicked.connect(lambda _: self.send_stage_cmd('get_speed'))

        # Add to layout
        layout_setup.addWidget(label_stage, 0, 0, 1, 1)
        layout_setup.addWidget(label_home, 0, 1, 1, 1)
        layout_setup.addWidget(btn_home, 0, 2, 1, 3)
        layout_setup.addWidget(label_speed, 1, 1, 1, 1)
        layout_setup.addWidget(spx_speed, 1, 2, 1, 1)
        layout_setup.addWidget(cbx_axis, 1, 3, 1, 1)
        layout_setup.addWidget(btn_set_speed, 1, 4, 1, 1)

        # Relative movements
        label_rel = QtWidgets.QLabel('Move relative:')
        label_rel_h = QtWidgets.QLabel('Horizontal')
        spx_rel_h = QtWidgets.QDoubleSpinBox()
        spx_rel_h.setDecimals(3)
        spx_rel_h.setMinimum(-300.0)
        spx_rel_h.setMaximum(300.0)
        spx_rel_h.setSuffix(' mm')
        btn_rel_h = QtWidgets.QPushButton('Move')
        btn_rel_h.clicked.connect(lambda _: self.send_stage_cmd('move_rel', cmd_data={'axis': 'x',
                                                                                      'distance': spx_rel_h.value(),
                                                                                      'unit': 'mm'}))
        btn_rel_h.clicked.connect(lambda _: self.send_stage_cmd('pos'))

        label_rel_v = QtWidgets.QLabel('Vertical')
        spx_rel_v = QtWidgets.QDoubleSpinBox()
        spx_rel_v.setDecimals(3)
        spx_rel_v.setMinimum(-300.0)
        spx_rel_v.setMaximum(300.0)
        spx_rel_v.setSuffix(' mm')
        btn_rel_v = QtWidgets.QPushButton('Move')
        btn_rel_v.clicked.connect(lambda _: self.send_stage_cmd('move_rel', cmd_data={'axis': 'y',
                                                                                      'distance': spx_rel_v.value(),
                                                                                      'unit': 'mm'}))
        btn_rel_v.clicked.connect(lambda _: self.send_stage_cmd('pos'))

        # Add to layout
        layout_setup.addWidget(label_rel, 2, 1, 1, 1)
        layout_setup.addWidget(label_rel_h, 2, 2, 1, 1)
        layout_setup.addWidget(spx_rel_h, 2, 3, 1, 1)
        layout_setup.addWidget(btn_rel_h, 2, 4, 1, 1)
        layout_setup.addWidget(label_rel_v, 3, 2, 1, 1)
        layout_setup.addWidget(spx_rel_v, 3, 3, 1, 1)
        layout_setup.addWidget(btn_rel_v, 3, 4, 1, 1)

        # Absolute movements
        label_abs = QtWidgets.QLabel('Move absolute:')
        label_abs_h = QtWidgets.QLabel('Horizontal')
        spx_abs_h = QtWidgets.QDoubleSpinBox()
        spx_abs_h.setDecimals(3)
        spx_abs_h.setMinimum(0.0)
        spx_abs_h.setMaximum(300.0)
        spx_abs_h.setSuffix(' mm')
        btn_abs_h = QtWidgets.QPushButton('Move')
        btn_abs_h.clicked.connect(lambda _: self.send_stage_cmd('move_abs', cmd_data={'axis': 'x',
                                                                                      'distance': spx_abs_h.value(),
                                                                                      'unit': 'mm'}))
        btn_abs_h.clicked.connect(lambda _: self.send_stage_cmd('pos'))

        label_abs_v = QtWidgets.QLabel('Vertical')
        spx_abs_v = QtWidgets.QDoubleSpinBox()
        spx_abs_v.setDecimals(3)
        spx_abs_v.setMinimum(0.0)
        spx_abs_v.setMaximum(300.0)
        spx_abs_v.setSuffix(' mm')
        btn_abs_v = QtWidgets.QPushButton('Move')
        btn_abs_v.clicked.connect(lambda _: self.send_stage_cmd('move_abs', cmd_data={'axis': 'y',
                                                                                      'distance': 300-spx_abs_v.value(),  # y-axis is inverted
                                                                                      'unit': 'mm'}))
        btn_abs_v.clicked.connect(lambda _: self.send_stage_cmd('pos'))

        # Add to layout
        layout_setup.addWidget(label_abs, 4, 1, 1, 1)
        layout_setup.addWidget(label_abs_h, 4, 2, 1, 1)
        layout_setup.addWidget(spx_abs_h, 4, 3, 1, 1)
        layout_setup.addWidget(btn_abs_h, 4, 4, 1, 1)
        layout_setup.addWidget(label_abs_v, 5, 2, 1, 1)
        layout_setup.addWidget(spx_abs_v, 5, 3, 1, 1)
        layout_setup.addWidget(btn_abs_v, 5, 4, 1, 1)

        # Layout daq
        label_daq = QtWidgets.QLabel('DAQ:')

        label_offset = QtWidgets.QLabel('Zero raw data offset:')
        # Button for auto zero offset
        self.btn_auto_zero = QtWidgets.QPushButton('Auto-zero offset')

        # Add to layout
        layout_setup.addWidget(label_daq, 6, 0, 1, 1)
        layout_setup.addWidget(label_offset, 6, 1, 1, 1)
        layout_setup.addWidget(self.btn_auto_zero, 6, 2, 1, 3)

        self.control_widget.layout().addLayout(layout_setup)
        self.control_widget.layout().addStretch()

    def _setup_scan(self):

        # Label for stage layout
        label_scan = QtWidgets.QLabel('Scan')
        self.scan_widget.layout().addWidget(label_scan, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

        # Layout for scan widgets
        layout_scan = QtWidgets.QGridLayout()

        # Step size
        label_step_size = QtWidgets.QLabel('Step size:')
        spx_step_size = QtWidgets.QDoubleSpinBox()
        spx_step_size.setMinimum(0.01)
        spx_step_size.setMaximum(10.0)
        spx_step_size.setValue(1.0)
        spx_step_size.setDecimals(3)
        spx_step_size.setSuffix(" mm")

        # Scan speed
        label_scan_speed = QtWidgets.QLabel('Scan speed:')
        spx_scan_speed = QtWidgets.QDoubleSpinBox()
        spx_scan_speed.setMinimum(10.)
        spx_scan_speed.setMaximum(200.)
        spx_scan_speed.setValue(80.0)
        spx_scan_speed.setDecimals(3)
        spx_scan_speed.setSuffix(' mm/s')

        # Beam current
        label_current = QtWidgets.QLabel('Approx. beam current:')
        edit_beam_current = QtWidgets.QLineEdit()
        edit_beam_current.setPlaceholderText('nA')
        edit_beam_current.setValidator(QtGui.QDoubleValidator())

        # Beam current
        label_aim_fluence = QtWidgets.QLabel('Aim fluence:')
        edit_aim_fluence = QtWidgets.QLineEdit()
        edit_aim_fluence.setPlaceholderText('p / cm^2')
        edit_aim_fluence.setValidator(QtGui.QDoubleValidator())

        # Start point
        label_start = QtWidgets.QLabel('Relative start point:')
        spx_start_x = QtWidgets.QDoubleSpinBox()
        spx_start_x.setRange(-300.,  300.)
        spx_start_x.setDecimals(3)
        spx_start_x.setPrefix('x: ')
        spx_start_x.setSuffix(' mm')
        spx_start_y = QtWidgets.QDoubleSpinBox()
        spx_start_y.setRange(-300., 300.)
        spx_start_y.setDecimals(3)
        spx_start_y.setPrefix('y: ')
        spx_start_y.setSuffix(" mm")

        # Start point
        label_end = QtWidgets.QLabel('Relative end point')
        spx_end_x = QtWidgets.QDoubleSpinBox()
        spx_end_x.setRange(-300., 300.)
        spx_end_x.setDecimals(3)
        spx_end_x.setPrefix('x: ')
        spx_end_x.setSuffix(' mm')
        spx_end_y = QtWidgets.QDoubleSpinBox()
        spx_end_y.setRange(-300., 300.)
        spx_end_y.setDecimals(3)
        spx_end_y.setPrefix('y: ')
        spx_end_y.setSuffix(' mm')

        # Stop button
        btn_stop = QtWidgets.QPushButton('STOP')
        btn_stop.clicked.connect(lambda _: self.send_stage_cmd('estop'))

        layout_scan.addWidget(label_step_size, 0, 0, 1, 1)
        layout_scan.addWidget(spx_step_size, 0, 1, 1, 2)
        layout_scan.addWidget(label_scan_speed, 1, 0, 1, 1)
        layout_scan.addWidget(spx_scan_speed, 1, 1, 1, 2)
        layout_scan.addWidget(label_current, 2, 0, 1, 1)
        layout_scan.addWidget(edit_beam_current, 2, 1, 1, 2)
        layout_scan.addWidget(label_aim_fluence, 3, 0, 1, 1)
        layout_scan.addWidget(edit_aim_fluence, 3, 1, 1, 2)
        layout_scan.addWidget(label_start, 4, 0, 1, 1)
        layout_scan.addWidget(spx_start_x, 4, 1, 1, 1)
        layout_scan.addWidget(spx_start_y, 4, 2, 1, 1)
        layout_scan.addWidget(label_end, 5, 0, 1, 1)
        layout_scan.addWidget(spx_end_x, 5, 1, 1, 1)
        layout_scan.addWidget(spx_end_y, 5, 2, 1, 1)

        btn_prepare = QtWidgets.QPushButton('Prepare scan')
        btn_prepare.clicked.connect(lambda _: self.prepare_scan(beam_current=float(edit_beam_current.text()),
                                                                aim_fluence=float(edit_aim_fluence.text()),
                                                                scan_speed=spx_scan_speed.value(),
                                                                step_size=spx_step_size.value(),
                                                                rel_start_point=(spx_start_x.value(),
                                                                                 spx_start_y.value()),
                                                                rel_end_point=(spx_end_x.value(),
                                                                               spx_end_y.value())))
        btn_start = QtWidgets.QPushButton('Start')
        btn_start.clicked.connect(lambda _: self.scanPrepared.emit(
            {'kappa': self.setup['daq'][self.setup['daq'].keys()[0]]['hardness_factor'], 'n_rows': self.n_rows}))
        btn_start.clicked.connect(lambda _: self.send_stage_cmd('scan'))

        btn_start.setEnabled(False)
        btn_stop.setEnabled(False)
        btn_prepare.clicked.connect(lambda _, btn=btn_start: btn.setEnabled(True))
        btn_prepare.clicked.connect(lambda _, btn=btn_stop: btn.setEnabled(True))

        btn_start.setStyleSheet('QPushButton {color: green;}')
        btn_stop.setStyleSheet('QPushButton {color: red;}')

        layout_scan.addWidget(btn_prepare, 6, 0, 1, 1)
        layout_scan.addWidget(btn_start, 6, 1, 1, 1)
        layout_scan.addWidget(btn_stop, 6, 2, 1, 1)

        self.scan_widget.layout().addLayout(layout_scan)
        self.scan_widget.layout().addStretch()

    def prepare_scan(self, beam_current, scan_speed, step_size, aim_fluence, rel_start_point, rel_end_point):

        # Calculate approx. fluence per scan
        self.fluence_per_scan = beam_current * 1e-9 / (1.60217733e-19 * scan_speed * step_size * 1e-2)

        n_scans = int(aim_fluence / self.fluence_per_scan)

        prep_data = {'rel_start_point': rel_start_point, 'rel_end_point': rel_end_point,
                     'n_scans': n_scans, 'scan_speed': scan_speed, 'step_size': step_size}

        self.send_stage_cmd('prepare', cmd_data=prep_data)

    def _setup_after(self):

        # Label for stage layout
        label_after = QtWidgets.QLabel('After-Scan')
        self.after_widget.layout().addWidget(label_after, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

        layout_after = QtWidgets.QGridLayout()

        label_scan_row = QtWidgets.QLabel('Scan row:')
        spbx_scan_row = QtWidgets.QSpinBox()
        #spbx_scan_row.setRange(0, self.n_rows)

        layout_after.addWidget(label_scan_row)
        layout_after.addWidget(spbx_scan_row)

        self.after_widget.layout().addLayout(layout_after)
        self.after_widget.layout().addStretch()

    def _setup_info(self):

        # Label for stage layout
        label_info = QtWidgets.QLabel('Info')
        self.info_widget.layout().addWidget(label_info, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

        # Label for current position position
        self.label_current_pos = QtWidgets.QLabel('Current position: ({} mm, {} mm)'.format(*self.current_pos))
        self.info_widget.layout().addWidget(self.label_current_pos)
        # Label for speeds position
        self.label_current_speed = QtWidgets.QLabel('Current speeds: ({} mm/s, {} mm/s)'.format(*self.current_speed))
        self.info_widget.layout().addWidget(self.label_current_speed)

        self.label_scan = QtWidgets.QLabel('Scan parameters:')
        self.info_widget.layout().addWidget(self.label_scan)
        self.info_widget.layout().addStretch()

    def send_stage_cmd(self, cmd, cmd_data=None):
        """Function emitting signal with command dict which is send to server in main"""
        self.sendStageCmd.emit({'target': 'stage', 'cmd': cmd, 'cmd_data': cmd_data})

    def update_position(self, pos):
        self.current_pos = pos
        self.label_current_pos.setText('Current position: ({:.3f} mm, {:.3f} mm)'.format(*[p * 1e3 for p in pos]))

    def update_speed(self, speed):
        self.current_speed = speed
        self.label_current_speed.setText('Current speeds: ({:.3f} mm/s, {:.3f} mm/s)'.format(*speed))

    def update_prepare(self, prep):

        self.step_size = prep['step_size']
        self.scan_speed = prep['scan_speed']
        self.n_rows = prep['n_rows']
        self.n_scans = prep['n_scans']

        self.label_scan.setText("Scan parameters:" + "\n\t".join([str(k) + ":{}".format(prep[k]) for k in prep]) + "\n\t" + "Est. fluence per scan:{} 1e12 p /cm^2".format(self.fluence_per_scan*1e-12))

    def set_read_only(self, read_only=True):

        # Disable/enable main widgets to set to read_only
        self.left_widget.setEnabled(not read_only)
        self.right_widget.setEnabled(not read_only)
        self.btn_ok.setEnabled(not read_only)
