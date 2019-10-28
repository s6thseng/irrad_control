from PyQt5 import QtWidgets, QtGui, QtCore
from collections import Iterable


class GridContainer(QtWidgets.QGroupBox):
    """Container widget for grouping widgets together in a grid layout."""

    def __init__(self, name, x_space=20, y_space=10, parent=None):
        super(GridContainer, self).__init__(parent)

        # Store name of container
        self.name = name

        # Contain all widgets
        self.widgets = {}

        # Set name
        self.setTitle(self.name)

        # Make grid layout
        self.grid = QtWidgets.QGridLayout()
        self.grid.setVerticalSpacing(y_space)
        self.grid.setHorizontalSpacing(x_space)
        self.setLayout(self.grid)

        # Counter for row and column
        self.cnt_row = 0
        self.cnt_col = {}

    def add_layout(self, layout):
        self.add_item(layout)

    def add_widget(self, widget):
        self.add_item(widget)

    def add_item(self, item):
        """Adds *widget* to container where *widget* can be any QWidget or an iterable of QWidgets."""

        error = False
        def check(x): return isinstance(x, QtWidgets.QWidget) or isinstance(x, QtWidgets.QLayout)

        if isinstance(item, Iterable):
            if not all(check(x) for x in item):
                error = True

        elif not check(item):
            # Only single widget is added to the current row
            error = True

        if error:
            raise TypeError("Only QWidgets and QLayouts can be added to layout!")
        else:
            self._add_item(item)

    def _add_item(self, item):
        """Actually adds widgets to grid layout"""

        try:
            n_widgets = len(item)
        except TypeError:
            n_widgets = 1

        if n_widgets == 1:
            # Catch edge case in which we get an iterable with only one widget e.g. item=[QLabel]
            try:
                item = item[0]
            except TypeError:
                pass
            self._add_to_grid(item, self.cnt_row, 0)
        else:
            # Loop over all widgets and add to layout
            for i, itm in enumerate(item):
                self._add_to_grid(itm, self.cnt_row, i)

        # Update
        self.cnt_col[self.cnt_row] = n_widgets
        self.cnt_row += 1

    def _add_to_grid(self, item, row, col):

        if isinstance(item, QtWidgets.QLayout):
            self.grid.addLayout(item, row, col)
        else:
            self.grid.addWidget(item, row, col)

    def get_widget_count(self, row):
        """Return number of widgets in *row*"""
        if row in self.cnt_col:
            return self.cnt_col[row]
        else:
            raise IndexError("Row {} does not exist. Existing rows: {}".format(row, self.cnt_row))

    def get_row_count(self):
        """Return number of rows"""
        return self.cnt_row

    def set_read_only(self, read_only=True, omit=None):
        """Sets all widgets to read only. If they don't have a readOnly-method, they're disabled"""

        omit = omit if isinstance(omit, Iterable) else [omit]

        # Loop over entire grid
        for row in range(self.cnt_row):
            for col in range(self.cnt_col[row]):
                # Get item at row, col
                item = self.grid.itemAtPosition(row, col)

                # Item is QSpacerItem or 0 (no item)
                if isinstance(item, QtWidgets.QSpacerItem) or item == 0:
                    pass

                # Check whether its QLayoutItem or QWidgetItem
                elif isinstance(item, QtWidgets.QWidgetItem):
                    # Extract widget and set read_only
                    _widget = item.widget()
                    if type(_widget) not in omit:
                        self.set_widget_read_only(widget=_widget, read_only=read_only)

                elif isinstance(item, QtWidgets.QLayoutItem):
                    # Loop over layout and disable widgets
                    _layout = item.layout()
                    for i in reversed(range(_layout.count())):
                        # Check whether its a QWidgetItem and not a Spacer etc
                        if isinstance(_layout.itemAt(i), QtWidgets.QWidgetItem):
                            _widget = _layout.itemAt(i).widget()
                            if type(_widget) not in omit:
                                self.set_widget_read_only(widget=_widget, read_only=read_only)
                else:
                    raise TypeError('Item must be either QWidgetItem or QLayoutItem. Found {}'.format(type(item)))

    @staticmethod
    def set_widget_read_only(widget, read_only=True):
        """Set widget to read only. Use widgets setReadOnly-method else just disable"""

        # We don't have to do anything with labels
        if not isinstance(widget, QtWidgets.QLabel):
            # Check if we have readOnly method
            if hasattr(widget, 'setReadOnly'):
                widget.setReadOnly(read_only)
            # If not, just disable
            else:
                widget.setEnabled(not read_only)

        # Set color palette to indicate status
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Base, QtCore.Qt.gray if read_only else QtCore.Qt.white)
        palette.setColor(QtGui.QPalette.Text, QtCore.Qt.darkGray if read_only else QtCore.Qt.black)
        widget.setPalette(palette)
