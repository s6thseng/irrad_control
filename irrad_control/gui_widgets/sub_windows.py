from PyQt5 import QtWidgets, QtCore, QtGui
from collections import OrderedDict


class ZmqSetupWindow(QtWidgets.QMainWindow):
    """Sub window for zmq settings"""

    zmqSetupChanged = QtCore.pyqtSignal(OrderedDict)

    def __init__(self, parent=None):
        super(ZmqSetupWindow, self).__init__(parent)

        self.window_title = '%sMQ setup' % u'\u00D8'

        self.default_ports = OrderedDict([('log', 8500), ('data', 8600), ('cmd', 8700), ('stage', 8800), ('temp', 8900)])

        self.ports = OrderedDict([(k, self.default_ports[k]) for k in self.default_ports])

        self.edits = {}

        self._init_ui()

    def _init_ui(self):

        self.setWindowTitle(self.window_title)
        # Make this window blocking parent window
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.screen = QtWidgets.QDesktopWidget().screenGeometry()
        self.resize(0.25 * self.screen.width(), 0.25 * self.screen.height())

        # Main widget
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setHorizontalSpacing(20)
        layout.setVerticalSpacing(10)
        layout.setAlignment(QtCore.Qt.AlignTop)
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        layout.addWidget(QtWidgets.QLabel('Ports:'), 0, 0, 1, 1)

        for i, port in enumerate(self.default_ports):
            label = QtWidgets.QLabel(port.capitalize())
            edit = QtWidgets.QLineEdit()
            edit.setValidator(QtGui.QIntValidator(1, int(2**16)))
            edit.setText(str(self.default_ports[port]))
            layout.addWidget(label, i+1, 1, 1, 1)
            layout.addWidget(edit, i+1, 2, 1, 1)

            self.edits[port] = edit

        btn_reset = QtWidgets.QPushButton('Reset')
        btn_reset.clicked.connect(lambda _: [self.edits[k].setText(str(self.default_ports[k])) for k in self.default_ports])
        layout.addWidget(btn_reset, 6, 0, 1, 1)

        btn_ok = QtWidgets.QPushButton('Ok')
        btn_ok.clicked.connect(lambda _: self._update_ports())
        btn_ok.clicked.connect(self.close)

        btn_cancel = QtWidgets.QPushButton('Cancel')
        btn_cancel.clicked.connect(self.close)

        layout.addWidget(btn_cancel, 6, 3, 1, 1)
        layout.addWidget(btn_ok, 6, 4, 1, 1)

    def _update_ports(self):

        for port in self.edits:
            self.ports[port] = int(self.edits[port].text())

        self.zmqSetupChanged.emit(self.ports)
