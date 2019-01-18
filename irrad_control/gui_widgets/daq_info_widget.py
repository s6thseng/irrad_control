from PyQt5 import QtWidgets, QtCore, QtGui
from irrad_control import ads1256, ro_scales


class DaqInfoWidget(QtWidgets.QWidget):
    """
    Widget to display all necessary information about the data acquisition such as the amount of ADCs, their channels
    and the respective raw data and the sampling rate and numbers of internal ADC averages. Also displays the hardware
    configuration of the RO electronics for each ADC such as the 5V full scale and channel type.
    """

    def __init__(self, daq_config, table_fontsize=(12, 14), parent=None):
        super(DaqInfoWidget, self).__init__(parent)

        # Init class attributes
        self.daq_config = daq_config

        # Data related per ADC
        self.adcs = self.daq_config.keys()
        self.channels = {}
        self.ch_types = {}
        self.n_channels = {}
        self.tables = {}

        # Timestamps per ADC
        self.refresh_timestamp = {}
        self.data_timestamp = {}

        # Check number of DAQ ADCs
        for adc in self.adcs:
            self.channels[adc] = self.daq_config[adc]['channels']
            self.ch_types[adc] = self.daq_config[adc]['types']
            self.n_channels[adc] = len(self.daq_config[adc]['channels'])

        # Info related per ADC
        self.n_digits = dict(zip(self.adcs, [3] * len(self.adcs)))
        self.refresh_interval = dict(zip(self.adcs, [1] * len(self.adcs)))
        self.unit = dict(zip(self.adcs, ['V'] * len(self.adcs)))

        # Data table fonts
        self.table_header_font = QtGui.QFont()
        self.table_header_font.setPointSize(table_fontsize[0])
        self.table_header_font.setBold(True)
        self.table_value_font = QtGui.QFont()
        self.table_value_font.setPointSize(table_fontsize[1])
        self.table_value_font.setBold(True)

        # Spacing
        self.h_space = 100
        self.v_space = 50

        # Init user interface
        self._init_ui()

    def _init_ui(self):
        """Init the user interface of the widget. Use one tab per ADC"""

        # Main layout of the widget
        self.main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.main_layout)

        # Main widget
        self.tabs = QtWidgets.QTabWidget()

        # Info labels for all ADCs
        self.data_rate_labels = {}
        self.sampling_rate_labels = {}
        self.num_avg_labels = {}
        self.full_scale_labels = {}

        # Loop over all ADCs
        for adc in self.adcs:

            # Make tab widget and layout in which info and data will be displayed
            tab_widget = QtWidgets.QWidget()
            tab_layout = QtWidgets.QVBoxLayout()
            tab_widget.setLayout(tab_layout)

            # Layout for info labels and widgets
            info_layout = QtWidgets.QGridLayout()

            # Fill info layout with labels and widgets
            # Check info in daq_config
            _cnfg = self.daq_config[adc]
            _srate_lbl = '' if 'sampling_rate' not in _cnfg else _cnfg['sampling_rate']
            _avgs_lbl = '' if 'sampling_rate' not in _cnfg else ads1256['avgs'][_cnfg['sampling_rate']]
            _ro_lbl = '' if 'ro_scale' not in _cnfg else ''.join([s for s in ro_scales.keys() if ro_scales[s] == _cnfg['ro_scale']])

            # Set labels
            self.data_rate_labels[adc] = QtWidgets.QLabel('Data rate :' + '\t' + 'Hz ')
            self.sampling_rate_labels[adc] = QtWidgets.QLabel('Sampling rate: %s sps' % _srate_lbl)
            self.num_avg_labels[adc] = QtWidgets.QLabel('Averages: %s' % _avgs_lbl)
            self.full_scale_labels[adc] = QtWidgets.QLabel('5V full-scale: %s' % _ro_lbl)

            # Tooltips of labels
            self.data_rate_labels[adc].setToolTip('Rate of incoming data of respective ADC')
            self.sampling_rate_labels[adc].setToolTip('Samples per second of the ADS1256')
            self.num_avg_labels[adc].setToolTip('Number of averages done by the ADS1256 for respective sampling rate')
            self.full_scale_labels[adc].setToolTip('5V full-scale current resolution of the readout electronics')

            # Helper widgets to change display of raw data
            # Spinbox to select refresh rate of data
            interval_spinbox = QtWidgets.QDoubleSpinBox()
            interval_spinbox.setPrefix('Refresh every ')
            interval_spinbox.setSuffix(' s')
            interval_spinbox.setDecimals(1)
            interval_spinbox.setRange(0, 10)  # max 10 s
            interval_spinbox.setValue(self.refresh_interval[adc])
            interval_spinbox.valueChanged.connect(lambda v, x=adc: self.update_interval(x, v))

            # Spinbox to adjust number of digits
            digit_spinbox = QtWidgets.QSpinBox()
            digit_spinbox.setPrefix('Digits: ')
            digit_spinbox.setRange(1, 10)  # max 10 decimals
            digit_spinbox.setValue(self.n_digits[adc])
            digit_spinbox.valueChanged.connect(lambda v, x=adc: self.update_digits(x, v))

            # Radio buttons in order to set unit in which raw data should be displayed
            unit_label = QtWidgets.QLabel('Unit:')
            volt_rb = QtWidgets.QRadioButton('V')
            volt_rb.setChecked(True)
            ampere_rb = QtWidgets.QRadioButton('nA')
            volt_rb.toggled.connect(lambda v, x=adc: self.update_unit(v, x, volt_rb.text()))
            ampere_rb.toggled.connect(lambda v, x=adc: self.update_unit(v, x, ampere_rb.text()))

            # Add to layout
            info_layout.addWidget(self.data_rate_labels[adc], 0, 0, 1, 1)
            info_layout.addWidget(self.sampling_rate_labels[adc], 1, 0, 1, 1)
            info_layout.addItem(QtWidgets.QSpacerItem(self.h_space, 0), 0, 1, 1, 2)
            info_layout.addWidget(self.num_avg_labels[adc], 0, 2, 1, 1)
            info_layout.addWidget(self.full_scale_labels[adc], 1, 2, 1, 1)
            info_layout.addItem(QtWidgets.QSpacerItem(self.h_space, 0), 0, 3, 1, 2)
            info_layout.addWidget(unit_label, 0, 4, 1 ,2)
            info_layout.addWidget(volt_rb, 1, 4, 1 ,1)
            info_layout.addWidget(ampere_rb, 1, 5, 1, 1)
            info_layout.addWidget(digit_spinbox, 0, 6, 1, 1)
            info_layout.addWidget(interval_spinbox, 1, 6, 1, 1)
            tab_layout.addLayout(info_layout)

            # Layout for table area
            table_layout = QtWidgets.QVBoxLayout()
            tab_layout.addLayout(table_layout)

            # Make table for ADC
            self.tables[adc] = self._setup_table(adc)

            for table in self.tables[adc]:
                table_layout.addWidget(table)

            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(tab_widget)

            self.tabs.addTab(scroll_area, adc)

        self.main_layout.addWidget(self.tabs)

    def _setup_table(self, adc):
        """Setup and return table widget(s) in order to display channel data of adc"""
        
        # Check how many tables are needed to display all channels
        total_tables = self._check_n_tables(adc)

        # Determine which table has how many columns
        cols_per_table, remnant = divmod(self.n_channels[adc], total_tables)
        cols_final = [cpt + 1 if (i + 1) <= remnant else cpt for i, cpt in enumerate([cols_per_table] * total_tables)]

        # Loop over tables and fill list
        tables = []
        for i in range(total_tables):
            table = QtWidgets.QTableWidget()
            table.showGrid()
            table.setRowCount(1)
            table.verticalHeader().setVisible(False)
            table.setColumnCount(cols_final[i])
            current_headers = self.channels[adc][sum(cols_final[:i]): sum(cols_final[:i + 1])]
            table.setHorizontalHeaderLabels([h + ' / ' + self.unit[adc] for h in current_headers])
            for j in range(table.columnCount()):
                table.horizontalHeaderItem(j).setToolTip('Channel of type %s' % self.ch_types[adc][j])
                table.horizontalHeaderItem(j).setFont(self.table_header_font)
                table.setItem(0, j, QtWidgets.QTableWidgetItem(format(0, '.{}f'.format(self.n_digits[adc]))))
                table.item(0, j).setTextAlignment(QtCore.Qt.AlignCenter)
                table.item(0, j).setFlags(QtCore.Qt.ItemIsEnabled)
                table.item(0, j).setFont(self.table_value_font)
                table.resizeColumnToContents(j)

            # Set minimum widths and stretch policies
            table.setMinimumWidth(sum([table.columnWidth(k) for k in range(table.columnCount())]))
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

            tables.append(table)

        return tables

    def _check_n_tables(self, adc):

        # make as many tables as necessary in order to display the data
        enough_tables = False
        total_cols = 0
        total_tables = 0

        # check how many tables are needed to display raw data
        while not enough_tables:
            table = QtWidgets.QTableWidget()
            table.setRowCount(1)
            n_cols = 1
            while n_cols <= (self.n_channels[adc] - total_cols):
                table.setColumnCount(n_cols)
                current_headers = [h + ' / ' + self.unit[adc] for h in self.channels[adc][total_cols: total_cols + n_cols]]
                table.setHorizontalHeaderLabels(current_headers)
                for j in range(table.columnCount()):
                    table.setItem(0, j, QtWidgets.QTableWidgetItem(format(0, '.{}f'.format(self.n_digits[adc]))))
                    table.resizeColumnToContents(j)

                if sum([table.columnWidth(i) for i in range(table.columnCount() + 1)]) > self.width():
                    break

                n_cols += 1

            total_tables += 1
            total_cols += n_cols

            if total_cols >= self.n_channels[adc]:
                enough_tables = True

        return total_tables

    def _update_tables(self, ch_data=None):
        """Helper func to update all tables at once"""
        for adc in self.adcs:
            self.update_table(adc, ch_data=ch_data)

    def update_digits(self, adc, digits):
        """Update the digits to display in table data"""
        self.n_digits[adc] = digits
        self._update_tables()

    def update_interval(self, adc, interval):
        """Update the data rate label"""
        self.refresh_interval[adc] = interval

    def update_unit(self, v, adc, unit):
        self.unit[adc] = unit if v else self.unit[adc]
        self._update_tables()

    def update_data(self, data):
        """Function handling incoming data and updating table widgets"""

        # Extract meta data and actual data
        meta_data, channel_data = data['meta'], data['data']

        # Name of ADC; first raw data will not have data rate
        adc, drate = meta_data['name'], 0 if 'data_rate' not in meta_data else meta_data['data_rate']

        # First incoming data sets is displayed and sets timestamp
        if adc not in self.refresh_timestamp:
            self.refresh_timestamp[adc] = self.refresh_interval[adc]

        # Timestamp, data rate and update
        timestamp = meta_data['timestamp']
        refresh_time = timestamp - self.refresh_timestamp[adc]

        # Only update widgets if it's time to refresh; if interval is 0, update all the time
        if refresh_time >= self.refresh_interval[adc] or self.refresh_interval[adc] == 0:
            self.update_drate(adc=adc, drate=drate)
            self.update_table(adc=adc, ch_data=channel_data)
            self.refresh_timestamp[adc] = timestamp

    def update_table(self, adc, ch_data=None):
        """Method updating table data per ADC"""

        # Loop over tables of adc
        for table in self.tables[adc]:
            # Loop over column index
            for i in range(table.columnCount()):
                # Get current column header text and strip data unit
                data_header = table.horizontalHeaderItem(i).text().split(' ')[0]
                # If channel data is none only update number of digits or unit
                if ch_data is None:
                    table.horizontalHeaderItem(i).setText(data_header + ' / ' + self.unit[adc])
                    table.item(0, i).setText(format(float(table.item(0, i).text()), '.{}f'.format(self.n_digits[adc])))
                # Update table entries with new data
                else:
                    if data_header in ch_data:
                        table.item(0, i).setText(format(self._calc(adc, ch_data[data_header]), '.{}f'.format(self.n_digits[adc])))

    def update_drate(self, adc, drate):
        """Update the data rate label"""
        self.data_rate_labels[adc].setText('Data rate: {} Hz'.format(format(drate, '.2f')))

    def update_srate(self, adc, srate):
        """Update the sampling rate label"""
        self.sampling_rate_labels[adc].setText('Sampling rate: {} sps'.format(srate))

    def update_num_avg(self, adc, num_avg):
        """Update the average number label"""
        self.num_avg_labels[adc].setText('Averages: {}'.format(num_avg))

    def update_scale(self, adc, scale):
        """Update the 5V full-scale label"""
        self.full_scale_labels[adc].setText('5V full-scale: {}'.format(scale))

    def _calc(self, adc, val):
        return val if self.unit[adc] == 'V' else (val / 5.0 * self.daq_config[adc]['ro_scale'])  # 5V from RO electronics