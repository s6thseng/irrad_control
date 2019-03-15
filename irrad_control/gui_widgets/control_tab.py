import os
import time
import zmq
import threading
from PyQt5 import QtWidgets, QtCore, QtGui


class IrradControl(QtWidgets.QWidget):
    """Control widget for the irradiation control software"""

    sendStageCmd = QtCore.pyqtSignal(dict)
    scanPrepared = QtCore.pyqtSignal(dict)

    def __init__(self, irrad_setup, parent=None):
        super(IrradControl, self).__init__(parent)

        # Layouts; split in quadrants
        self.main_layout = QtWidgets.QHBoxLayout()
        self.left_layout = QtWidgets.QVBoxLayout()
        self.right_layout = QtWidgets.QVBoxLayout()

        # Add left and right to main
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.right_layout)

        # Make quadrants
        self.info_layout = QtWidgets.QVBoxLayout()
        self.stage_layout = QtWidgets.QVBoxLayout()
        self.scan_layout = QtWidgets.QVBoxLayout()
        self.after_layout = QtWidgets.QVBoxLayout()

        # Add to main
        self.left_layout.addLayout(self.stage_layout)
        self.left_layout.addLayout(self.after_layout)
        self.right_layout.addLayout(self.scan_layout)
        self.right_layout.addLayout(self.info_layout)
        
        # Add main layout to widget layout and add ok button
        self.setLayout(self.main_layout)

        # General attributes
        self.setup = irrad_setup

        # Attributes for the stage
        self.home_position = [0.0, 0.0]
        self.current_pos = [0.0, 0.0]
        self.current_speed = [0.0, 0.0]
        self.scan_speed = None
        self.step_size = None
        self.n_rows = None

        # Setup the widgets for each quadrant
        self._setup_stage()
        self._setup_scan()
        self._setup_after()
        self._setup_info()

    def _setup_stage(self):

        # Label for stage layout
        label_stage = QtWidgets.QLabel('XY-Stage')
        self.stage_layout.addWidget(label_stage, alignment=QtCore.Qt.AlignHCenter)

        # Grid layout to group widgets
        layout_movements = QtWidgets.QGridLayout()

        # Button to home the device
        btn_home = QtWidgets.QPushButton('Home axes')
        btn_home.clicked.connect(lambda _: self.send_stage_cmd('home'))

        # movement speed
        label_speed = QtWidgets.QLabel('Set speed:')
        spx_speed = QtWidgets.QDoubleSpinBox()
        spx_speed.setMinimum(0.000303)
        spx_speed.setMaximum(205.)
        spx_speed.setDecimals(3)
        spx_speed.setSuffix(" mm/s")
        cbx_axis = QtWidgets.QComboBox()
        cbx_axis.addItems(["x", "y"])
        btn_set_speed = QtWidgets.QPushButton('Set speed')
        btn_set_speed.clicked.connect(lambda _: self.send_stage_cmd('set_speed', cmd_data={'axis': cbx_axis.currentText(),
                                                                                           'speed': spx_speed.value(),
                                                                                           'unit': "mm/s"}))
        btn_set_speed.clicked.connect(lambda _: self.send_stage_cmd('get_speed'))

        # Add to layout
        layout_movements.addWidget(btn_home, 0, 0, 1, 4)
        layout_movements.addWidget(label_speed, 1, 0, 1, 1)
        layout_movements.addWidget(spx_speed, 2, 1, 1, 1)
        layout_movements.addWidget(cbx_axis, 2, 2, 1, 1)
        layout_movements.addWidget(btn_set_speed, 2, 3, 1, 1)

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
        layout_movements.addWidget(label_rel, 3, 0, 1, 1)
        layout_movements.addWidget(label_rel_h, 4, 1, 1, 1)
        layout_movements.addWidget(spx_rel_h, 4, 2, 1, 1)
        layout_movements.addWidget(btn_rel_h, 4, 3, 1, 1)
        layout_movements.addWidget(label_rel_v, 5, 1, 1, 1)
        layout_movements.addWidget(spx_rel_v, 5, 2, 1, 1)
        layout_movements.addWidget(btn_rel_v, 5, 3, 1, 1)

        # Absolute movements
        label_abs = QtWidgets.QLabel('Move absolute:')
        label_abs_h = QtWidgets.QLabel('Horizontal')
        spx_abs_h = QtWidgets.QDoubleSpinBox()
        spx_abs_h.setDecimals(3)
        spx_abs_h.setMinimum(0.0)
        spx_abs_h.setMaximum(300.0)
        spx_abs_h.setSuffix('mm')
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
        spx_abs_v.setSuffix('mm')
        btn_abs_v = QtWidgets.QPushButton('Move')
        btn_abs_v.clicked.connect(lambda _: self.send_stage_cmd('move_abs', cmd_data={'axis': 'y',
                                                                                      'distance': 300-spx_abs_v.value(),  # y-axis is inverted
                                                                                      'unit': 'mm'}))
        btn_abs_v.clicked.connect(lambda _: self.send_stage_cmd('pos'))

        # Add to layout
        layout_movements.addWidget(label_abs, 6, 0, 1, 1)
        layout_movements.addWidget(label_abs_h, 7, 1, 1, 1)
        layout_movements.addWidget(spx_abs_h, 7, 2, 1, 1)
        layout_movements.addWidget(btn_abs_h, 7, 3, 1, 1)
        layout_movements.addWidget(label_abs_v, 8, 1, 1, 1)
        layout_movements.addWidget(spx_abs_v, 8, 2, 1, 1)
        layout_movements.addWidget(btn_abs_v, 8, 3, 1, 1)

        self.stage_layout.addLayout(layout_movements)

    def _setup_scan(self):

        # Label for stage layout
        label_scan = QtWidgets.QLabel('Scan')
        self.scan_layout.addWidget(label_scan, alignment=QtCore.Qt.AlignHCenter)

        # Layout for scan widgets
        layout_scan = QtWidgets.QGridLayout()

        # Step size
        label_step_size = QtWidgets.QLabel('Step size')
        spx_step_size = QtWidgets.QDoubleSpinBox()
        spx_step_size.setMinimum(0.01)
        spx_step_size.setMaximum(10.0)
        spx_step_size.setDecimals(3)
        spx_step_size.setSuffix("mm")

        # Scan speed
        label_scan_speed = QtWidgets.QLabel('Scan speed')
        spx_scan_speed = QtWidgets.QDoubleSpinBox()
        spx_scan_speed.setMinimum(40.)
        spx_scan_speed.setMaximum(200.)
        spx_scan_speed.setDecimals(3)
        spx_scan_speed.setSuffix("mm/s")

        # Beam current
        label_current = QtWidgets.QLabel('Approx. beam current')
        edit_beam_current = QtWidgets.QLineEdit()
        edit_beam_current.setValidator(QtGui.QDoubleValidator())
        label_beam_unit = QtWidgets.QLabel("nA")

        # Beam current
        label_aim_fluence = QtWidgets.QLabel('Aim fluence')
        edit_aim_fluence = QtWidgets.QLineEdit()
        edit_aim_fluence.setValidator(QtGui.QDoubleValidator())
        label_fl_unit = QtWidgets.QLabel("p / cm^2")

        # Start point
        label_start = QtWidgets.QLabel('Relative start point')
        spx_start_x = QtWidgets.QDoubleSpinBox()
        spx_start_x.setRange(-300.,  300.)
        spx_start_x.setDecimals(3)
        spx_start_x.setSuffix("mm")
        spx_start_y = QtWidgets.QDoubleSpinBox()
        spx_start_y.setRange(-300., 300.)
        spx_start_y.setDecimals(3)
        spx_start_y.setSuffix("mm")

        # Start point
        label_end = QtWidgets.QLabel('Relative end point')
        spx_end_x = QtWidgets.QDoubleSpinBox()
        spx_end_x.setRange(-300., 300.)
        spx_end_x.setDecimals(3)
        spx_end_x.setSuffix("mm")
        spx_end_y = QtWidgets.QDoubleSpinBox()
        spx_end_y.setRange(-300., 300.)
        spx_end_y.setDecimals(3)
        spx_end_y.setSuffix("mm")

        # Stop button
        btn_stop = QtWidgets.QPushButton("STOP")
        btn_stop.clicked.connect(lambda _: self.send_stage_cmd('estop'))

        layout_scan.addWidget(label_step_size, 0, 0, 1, 1)
        layout_scan.addWidget(spx_step_size, 0, 1, 1, 1)
        layout_scan.addWidget(label_scan_speed, 1, 0, 1, 1)
        layout_scan.addWidget(spx_scan_speed, 1, 1, 1, 1)
        layout_scan.addWidget(label_current, 2, 0, 1, 1)
        layout_scan.addWidget(edit_beam_current, 2, 1, 1, 1)
        layout_scan.addWidget(label_beam_unit, 2, 2, 1, 1)
        layout_scan.addWidget(label_aim_fluence, 3, 0, 1, 1)
        layout_scan.addWidget(edit_aim_fluence, 3, 1, 1, 1)
        layout_scan.addWidget(label_fl_unit, 3, 2, 1, 1)
        layout_scan.addWidget(label_start, 4, 0, 1, 1)
        layout_scan.addWidget(spx_start_x, 4, 1, 1, 1)
        layout_scan.addWidget(spx_start_y, 4, 2, 1, 1)
        layout_scan.addWidget(label_end, 5, 0, 1, 1)
        layout_scan.addWidget(spx_end_x, 5, 1, 1, 1)
        layout_scan.addWidget(spx_end_y, 5, 2, 1, 1)
        layout_scan.addWidget(btn_stop, 6, 0, 1, 3)

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

        layout_scan.addWidget(btn_prepare)
        layout_scan.addWidget(btn_start)

        self.scan_layout.addLayout(layout_scan)

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
        self.after_layout.addWidget(label_after, alignment=QtCore.Qt.AlignHCenter)

    def _setup_info(self):

        # Label for stage layout
        label_info = QtWidgets.QLabel('Info')
        self.info_layout.addWidget(label_info, alignment=QtCore.Qt.AlignHCenter)

        # Label for home position
        self.label_home_pos = QtWidgets.QLabel('Home position: ({} m, {} m)'.format(*self.home_position))
        self.info_layout.addWidget(self.label_home_pos)
        # Label for current position position
        self.label_current_pos = QtWidgets.QLabel('Current position: ({} m, {} m)'.format(*self.home_position))
        self.info_layout.addWidget(self.label_current_pos)
        # Label for speeds position
        self.label_current_speed = QtWidgets.QLabel('Current speeds: ({} mm/s, {} mm/s)'.format(*self.current_speed))
        self.info_layout.addWidget(self.label_current_speed)

        self.label_scan = QtWidgets.QLabel('Scan parameters:')
        self.info_layout.addWidget(self.label_scan)

    def send_stage_cmd(self, cmd, cmd_data=None):
        """Function emitting signal with command dict which is send to server in main"""
        self.sendStageCmd.emit({'target': 'stage', 'cmd': cmd, 'cmd_data': cmd_data})

    def update_position(self, pos):
        self.current_pos = pos
        self.label_current_pos.setText('Current position: ({} m, {} m)'.format(*pos))

    def update_speed(self, speed):
        self.current_speed = speed
        self.label_current_speed.setText('Current speeds: ({} mm/s, {} mm/s)'.format(*speed))

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
