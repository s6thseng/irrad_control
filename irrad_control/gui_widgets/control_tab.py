import time
from PyQt5 import QtWidgets, QtCore
from collections import OrderedDict


class IrradControl(QtWidgets.QWidget):
    """Control widget for the irradiation control software"""

    sendCmd = QtCore.pyqtSignal(dict)

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
        self.aim_fluence = None
        self.beam_current = None
        self.min_scan_current = None
        self.scan_params = OrderedDict()
        self.beam_down = False
        self.beam_down_timer = None

        # Setup the widgets for each quadrant
        self._setup_info()
        self._setup_control()
        self._setup_scan()
        self._setup_after()

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
        btn_home.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='home'))

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
        btn_set_speed.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                              cmd='set_speed',
                                                              cmd_data={'axis': cbx_axis.currentText(),
                                                                        'speed': spx_speed.value(),
                                                                        'unit': 'mm/s'}))
        btn_set_speed.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='get_speed'))

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
        btn_rel_h.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                          cmd='move_rel',
                                                          cmd_data={'axis': 'x',
                                                                    'distance': spx_rel_h.value(),
                                                                    'unit': 'mm'}))
        btn_rel_h.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='pos'))

        label_rel_v = QtWidgets.QLabel('Vertical')
        spx_rel_v = QtWidgets.QDoubleSpinBox()
        spx_rel_v.setDecimals(3)
        spx_rel_v.setMinimum(-300.0)
        spx_rel_v.setMaximum(300.0)
        spx_rel_v.setSuffix(' mm')
        btn_rel_v = QtWidgets.QPushButton('Move')
        btn_rel_v.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                          cmd='move_rel',
                                                          cmd_data={'axis': 'y',
                                                                    'distance': spx_rel_v.value(),
                                                                    'unit': 'mm'}))
        btn_rel_v.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='pos'))

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
        btn_abs_h.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                          cmd='move_abs',
                                                          cmd_data={'axis': 'x',
                                                                    'distance': spx_abs_h.value(),
                                                                    'unit': 'mm'}))
        btn_abs_h.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='pos'))

        label_abs_v = QtWidgets.QLabel('Vertical')
        spx_abs_v = QtWidgets.QDoubleSpinBox()
        spx_abs_v.setDecimals(3)
        spx_abs_v.setMinimum(0.0)
        spx_abs_v.setMaximum(300.0)
        spx_abs_v.setSuffix(' mm')
        btn_abs_v = QtWidgets.QPushButton('Move')
        btn_abs_v.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                          cmd='move_abs',
                                                          cmd_data={'axis': 'y',
                                                                    'distance': 300-spx_abs_v.value(),  # y-axis is inverted
                                                                    'unit': 'mm'}))
        btn_abs_v.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='pos'))

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
        self.layout_scan = QtWidgets.QGridLayout()

        # Step size
        label_step_size = QtWidgets.QLabel('Step size:')
        spx_step_size = QtWidgets.QDoubleSpinBox()
        spx_step_size.setMinimum(0.01)
        spx_step_size.setMaximum(10.0)
        spx_step_size.setDecimals(3)
        spx_step_size.setSuffix(" mm")
        spx_step_size.valueChanged.connect(lambda v: self.update_scan_parameters(step_size=v))
        spx_step_size.setValue(1.0)

        # Scan speed
        label_scan_speed = QtWidgets.QLabel('Scan speed:')
        spx_scan_speed = QtWidgets.QDoubleSpinBox()
        spx_scan_speed.setMinimum(10.)
        spx_scan_speed.setMaximum(200.)
        spx_scan_speed.setDecimals(3)
        spx_scan_speed.setSuffix(' mm/s')
        spx_scan_speed.valueChanged.connect(lambda v: self.update_scan_parameters(scan_speed=v))
        spx_scan_speed.setValue(80.0)

        # Beam current
        label_min_current = QtWidgets.QLabel('Minimum scan current:')
        label_min_current.setToolTip("")
        spx_min_current = QtWidgets.QSpinBox()
        spx_min_current.setRange(0, 1000)
        spx_min_current.setSingleStep(50)
        spx_min_current.setSuffix(' nA')
        spx_min_current.setValue(0)
        spx_min_current.valueChanged.connect(lambda v: self.set_min_current(v))

        # Fluence
        label_aim_fluence = QtWidgets.QLabel('Aim fluence:')
        spx_fluence_val = QtWidgets.QDoubleSpinBox()
        spx_fluence_val.setRange(1e-3, 10)
        spx_fluence_val.setDecimals(3)
        spx_fluence_exp = QtWidgets.QSpinBox()
        spx_fluence_exp.setPrefix('e ')
        spx_fluence_exp.setSuffix(' p / cm^2')
        spx_fluence_exp.setRange(10, 20)
        spx_fluence_val.valueChanged.connect(lambda v, e=spx_fluence_exp: self.set_aim_fluence(v, e.value()))
        spx_fluence_exp.valueChanged.connect(lambda e, v=spx_fluence_val: self.set_aim_fluence(v.value(), e))
        spx_fluence_val.setValue(1)
        spx_fluence_exp.setValue(13)


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
        spx_start_x.valueChanged.connect(lambda v: self.update_scan_parameters(rel_start_point=(v,
                                                                                                spx_start_y.value())))
        spx_start_y.valueChanged.connect(lambda v: self.update_scan_parameters(rel_start_point=(spx_start_x.value(),
                                                                                                v)))
        spx_start_x.valueChanged.emit(0.0)

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
        spx_end_x.valueChanged.connect(lambda v: self.update_scan_parameters(rel_end_point=(v, spx_end_y.value())))
        spx_end_y.valueChanged.connect(lambda v: self.update_scan_parameters(rel_end_point=(spx_end_x.value(), v)))
        spx_end_x.valueChanged.emit(0.0)

        self.layout_scan.addWidget(label_step_size, 0, 0, 1, 1)
        self.layout_scan.addWidget(spx_step_size, 0, 1, 1, 2)
        self.layout_scan.addWidget(label_scan_speed, 1, 0, 1, 1)
        self.layout_scan.addWidget(spx_scan_speed, 1, 1, 1, 2)
        self.layout_scan.addWidget(label_min_current, 2, 0, 1, 1)
        self.layout_scan.addWidget(spx_min_current, 2, 1, 1, 2)
        self.layout_scan.addWidget(label_aim_fluence, 3, 0, 1, 1)
        self.layout_scan.addWidget(spx_fluence_val, 3, 1, 1, 1)
        self.layout_scan.addWidget(spx_fluence_exp, 3, 2, 1, 1)
        self.layout_scan.addWidget(label_start, 4, 0, 1, 1)
        self.layout_scan.addWidget(spx_start_x, 4, 1, 1, 1)
        self.layout_scan.addWidget(spx_start_y, 4, 2, 1, 1)
        self.layout_scan.addWidget(label_end, 5, 0, 1, 1)
        self.layout_scan.addWidget(spx_end_x, 5, 1, 1, 1)
        self.layout_scan.addWidget(spx_end_y, 5, 2, 1, 1)

        self.btn_start = QtWidgets.QPushButton('START')
        self.btn_start.setToolTip("Start scan.")

        self.btn_start.clicked.connect(lambda _: self.send_cmd(target='stage',
                                                               cmd='prepare',
                                                               cmd_data=self.scan_params))

        self.btn_finish = QtWidgets.QPushButton('FINISH')
        self.btn_finish.setToolTip("Finish the scan. Allow remaining rows of current scan to be scanned before finishing.")
        self.btn_finish.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='finish'))

        # Stop button
        self.btn_stop = QtWidgets.QPushButton('STOP')
        self.btn_stop.setToolTip("Immediately cancel scan and return to origin from where scan started.")
        self.btn_stop.clicked.connect(lambda _: self.send_cmd(target='stage', cmd='stop'))

        self.btn_start.setStyleSheet('QPushButton {color: green;}')
        self.btn_finish.setStyleSheet('QPushButton {color: orange;}')
        self.btn_stop.setStyleSheet('QPushButton {color: red;}')

        self.layout_scan.addWidget(self.btn_start, 6, 0, 1, 1)
        self.layout_scan.addWidget(self.btn_finish, 6, 1, 1, 1)
        self.layout_scan.addWidget(self.btn_stop, 6, 2, 1, 1)

        self.scan_widget.layout().addLayout(self.layout_scan)
        self.scan_widget.layout().addStretch()

    def _setup_after(self):

        # Label for stage layout
        label_after = QtWidgets.QLabel('After-Scan')
        self.after_widget.layout().addWidget(label_after, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)

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
        # Label for scan speed
        self.label_stage_state = QtWidgets.QLabel('Stage status:')
        self.info_widget.layout().addWidget(self.label_stage_state)
        # Label for scan speed
        self.label_fluence_row = QtWidgets.QLabel('Fluence in previous row:')
        self.info_widget.layout().addWidget(self.label_fluence_row)
        self.label_fluence_scan = QtWidgets.QLabel('Fluence over completed scans:')
        self.info_widget.layout().addWidget(self.label_fluence_scan)
        self.label_n_scans = QtWidgets.QLabel('Estimated remaining scans:')
        self.info_widget.layout().addWidget(self.label_n_scans)
        self.label_scan = QtWidgets.QLabel('Scan parameters:\n\t')
        self.label_scan_dict = {}
        self.info_widget.layout().addWidget(self.label_scan)

        self.info_widget.layout().addStretch()

    def send_cmd(self, target, cmd, cmd_data=None):
        """Function emitting signal with command dict which is send to server in main"""
        self.sendCmd.emit({'target': target, 'cmd': cmd, 'cmd_data': cmd_data})

    def set_aim_fluence(self, nominal, exponent):
        self.aim_fluence = nominal * 10**exponent

    def set_min_current(self, min_current):
        self.min_scan_current = min_current * 1e-9  # Nano ampere

    def check_no_beam(self):

        if self.min_scan_current is not None:

            if self.beam_current < self.min_scan_current:

                self.beam_down_timer = time.time()

                if not self.beam_down:
                    self.send_cmd('stage', 'no_beam', True)
                    self.beam_down = True

            else:
                if self.beam_down:
                    if time.time() - self.beam_down_timer > 1.0:
                        self.send_cmd('stage', 'no_beam', False)
                        self.beam_down = False

    def update_scan_parameters(self, **params):

        # Update dict
        self.scan_params.update(params)

        for k in params:
            try:
                sfx = self.sender().suffix()
            except Exception:
                sfx = ""
            if k == 'rows':
                continue
            self.label_scan_dict[k] = '{}: {} {}'.format(k, self.scan_params[k], sfx)

        new_l = 'Scan parameters:\n'
        for i, n in enumerate(self.scan_params):
            if n == 'rows':
                continue
            new_l += '  ' + self.label_scan_dict[n] + ('\n' if (i+1) % 3 == 0 else '  ')

        self.label_scan.setText(new_l)

    def update_position(self, pos):
        self.current_pos = pos
        self.label_current_pos.setText('Current position: ({:.3f} mm, {:.3f} mm)'.format(*[p * 1e3 for p in pos]))

    def update_stage_status(self, status):
        self.label_stage_state.setText('Stage status: {}'.format(status))

    def update_speed(self, speed):
        self.current_speed = speed
        self.label_current_speed.setText('Current speeds: ({:.3f} mm/s, {:.3f} mm/s)'.format(*speed))

    def update_fluence(self, fluence, type_='row'):
        if type_ == 'row':
            self.label_fluence_row.setText('Fluence previous row: {:.3E} p/cm^2'.format(fluence))
        else:
            self.label_fluence_scan.setText('Fluence complete scans: {:.3E} p/cm^2'.format(fluence))

    def update_n_scans(self, n_scans):
        self.label_n_scans.setText('Estimated remaining scans: {}'.format(n_scans))

    def set_read_only(self, layout, read_only=True):

        for i in reversed(range(layout.count())):
            if isinstance(layout.itemAt(i), QtWidgets.QWidgetItem):
                w = layout.itemAt(i).widget()
                if not isinstance(w, QtWidgets.QPushButton):
                    w.setEnabled(not read_only)

    def scan_actions(self, status='started'):

        flag = True if status == 'started' else False

        self.set_read_only(self.layout_scan, read_only=flag)
        self.btn_start.setEnabled(not flag)

        self.control_widget.setDisabled(flag)
