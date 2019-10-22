from PyQt5 import QtWidgets
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
