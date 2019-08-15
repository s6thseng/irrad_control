from PyQt5 import QtWidgets, QtGui
from collections import OrderedDict


class LoggingTabWidget(QtWidgets.QTabWidget):

    def __init__(self, parent=None):
        super(LoggingTabWidget, self).__init__(parent)

        # Orientation of tabs on the left side; "West" == 2
        self.setTabPosition(0)

        # Available tabs and their priority
        self.log_tabs = OrderedDict([('DEBUG', 0), ('INFO', 1), ('WARNING', 2), ('ERROR', 3)])

        # QPlainTextWidgets used for writing log to
        self.log_consoles = {}

        # Style for icons
        self._style = QtWidgets.qApp.style()

        self.currentChanged.connect(lambda idx: self._clear_icon(idx))

        self._init_tabs()

    def _clear_icon(self, tab_idx):
        self.setTabIcon(tab_idx, self._get_icon('CLEAR'))

    def _get_icon(self, level):

        # Icons
        log_icons = {'DEBUG': self._style.SP_MessageBoxInformation,
                     'INFO': self._style.SP_MessageBoxInformation,
                     'WARNING': self._style.SP_MessageBoxWarning,
                     'ERROR': self._style.SP_MessageBoxCritical,
                     'ELSE': self._style.SP_MessageBoxQuestion}

        if level in log_icons:
            return self._style.standardIcon(log_icons[level])

        return QtGui.QIcon()

    def _init_tabs(self):

        for i, tab in enumerate(self.log_tabs.keys()):
            self.log_consoles[tab] = QtWidgets.QPlainTextEdit()
            self.log_consoles[tab].setReadOnly(True)
            self.addTab(self.log_consoles[tab], tab)

    def _check_level(self, log):
        return [level for level in self.log_tabs.keys() if level in log.upper()]

    def write_log(self, log):

        level = self._check_level(log)

        # None of the available levels found, e.g. CRITICAL or NOTSET; log to ERROR and give ? as icon
        if len(level) != 1:

            # Log to error console
            self.log_consoles['ERROR'].appendPlainText(log)

            # Indicate new event with icon if we're not looking at respective tab
            if self.currentIndex() != self.log_tabs['ERROR']:
                self.setTabIcon(self.log_tabs['ERROR'], self._get_icon('ELSE'))

        else:
            level = level[0]

            self.log_consoles[level].appendPlainText(log)

            if self.currentIndex() != self.log_tabs[level]:
                self.setTabIcon(self.log_tabs[level], self._get_icon(level))