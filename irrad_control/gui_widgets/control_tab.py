import os
import time
import zmq
import threading
from PyQt5 import QtWidgets, QtCore, QtGui


class IrradControl(QtWidgets.QWidget):
    """Control widget for the irradiation control software"""

    sendStageCmd = QtCore.pyqtSignal(dict)

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
        self.home_position = (0.0, 0.0)
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

        # Set home position; default is 0, 0
        label_home = QtWidgets.QLabel('Set home position:')
        label_current_pos = QtWidgets.QLabel('Use current position as home')

        btn_set_current = QtWidgets.QPushButton('Set current position')
        label_manual_pos = QtWidgets.QLabel('Set home position manually')
        spx_home_h = QtWidgets.QDoubleSpinBox()
        spx_home_h.setPrefix('Horizontal ')
        spx_home_h.setDecimals(3)
        spx_home_h.setMinimum(0.0)
        spx_home_h.setMaximum(300.0)
        spx_home_h.setSuffix(' mm')
        spx_home_v = QtWidgets.QDoubleSpinBox()
        spx_home_v.setPrefix('Vertical ')
        spx_home_v.setDecimals(3)
        spx_home_v.setMinimum(0.0)
        spx_home_v.setMaximum(300.0)
        spx_home_v.setSuffix(' mm')
        btn_set_manual = QtWidgets.QPushButton('Set position')
        btn_set_manual.clicked.connect(lambda _: self.label_home_pos.setText('Home position: ({} mm, {} mm)'.format(spx_home_h.value(),
                                                                                                                    spx_home_v.value())))

        # Add to layout
        layout_movements.addWidget(label_home, 0, 0, 1, 1)
        layout_movements.addWidget(label_current_pos, 1, 1, 1, 1)
        layout_movements.addWidget(btn_set_current, 1, 2, 1, 3)
        layout_movements.addWidget(label_manual_pos, 2, 1, 1, 1)
        layout_movements.addWidget(spx_home_h, 2, 2, 1, 1)
        layout_movements.addWidget(spx_home_v, 2, 3, 1, 1)
        layout_movements.addWidget(btn_set_manual, 2, 4, 1, 1)

        # Relative movements
        label_rel = QtWidgets.QLabel('Move relative:')
        label_rel_h = QtWidgets.QLabel('Horizontal')
        spx_rel_h = QtWidgets.QDoubleSpinBox()
        spx_rel_h.setDecimals(3)
        spx_rel_h.setMinimum(-300.0)
        spx_rel_h.setMaximum(300.0)
        spx_rel_h.setSuffix(' mm')

        btn_rel_h = QtWidgets.QPushButton('Move')
        label_rel_v = QtWidgets.QLabel('Vertical')
        spx_rel_v = QtWidgets.QDoubleSpinBox()
        spx_rel_v.setDecimals(3)
        spx_rel_v.setMinimum(-300.0)
        spx_rel_v.setMaximum(300.0)
        spx_rel_v.setSuffix(' mm')
        btn_rel_v = QtWidgets.QPushButton('Move')

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
        label_abs_v = QtWidgets.QLabel('Vertical')
        spx_abs_v = QtWidgets.QDoubleSpinBox()
        spx_abs_v.setDecimals(3)
        spx_abs_v.setMinimum(0.0)
        spx_abs_v.setMaximum(300.0)
        spx_abs_v.setSuffix('mm')
        btn_abs_v = QtWidgets.QPushButton('Move')

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

    def _setup_after(self):

        # Label for stage layout
        label_after = QtWidgets.QLabel('After-Scan')
        self.after_layout.addWidget(label_after, alignment=QtCore.Qt.AlignHCenter)

    def _setup_info(self):

        # Label for stage layout
        label_info = QtWidgets.QLabel('Info')
        self.info_layout.addWidget(label_info, alignment=QtCore.Qt.AlignHCenter)

        # Label for home position
        self.label_home_pos = QtWidgets.QLabel('Home position: ({} mm, {} mm)'.format(*self.home_position))
        self.info_layout.addWidget(self.label_home_pos)
        # Label for home position
        self.label_current_pos = QtWidgets.QLabel('Current position: ({} mm, {} mm)'.format(*self.home_position))
        self.info_layout.addWidget(self.label_home_pos)

    def send_stage_cmd(self, cmd, cmd_data=None):
        """Function emitting signal with command dict which is send to server in main"""
        self.sendStageCmd.emit({'target': 'stage', 'cmd': cmd, 'cmd_data': cmd_data})


    def set_read_only(self, read_only=True):

        # Disable/enable main widgets to set to read_only
        self.left_widget.setEnabled(not read_only)
        self.right_widget.setEnabled(not read_only)
        self.btn_ok.setEnabled(not read_only)
