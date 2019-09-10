import os
import zmq
import time
import multiprocessing
import logging
import yaml
import numpy as np
import tables as tb
from zmq.log import handlers
from irrad_control import roe_output, xy_stage_stats, config_path
from collections import defaultdict


class IrradInterpreter(multiprocessing.Process):
    """Implements an interpreter process"""

    def __init__(self, setup, name=None):
        super(IrradInterpreter, self).__init__()

        """
        IMPORTANT:
        The attributes initialized in here are only available as COPIES in the run()-method.
        In order to change attributes during runtime use multiprocessing.Event objects or queues. 
        """

        # Set name of this interpreter process
        self.name = 'interpreter' if name is None else name

        # Set the maximum table length before flushing data to hard drive
        self._max_buf_len = 1e2

        self.stage_stats = xy_stage_stats.copy()

        # Attributes to interact with the actual process stuff running within run()
        self.stop_recv_data = multiprocessing.Event()
        self.stop_write_data = multiprocessing.Event()
        self.is_receiving = multiprocessing.Event()
        self.xy_stage_maintenance = multiprocessing.Event()
        self.auto_zero = multiprocessing.Event()

        # General setup
        self.irrad_setup = setup
        self.tcp_setup = setup['tcp']
        self.adc_names = setup['daq'].keys()
        self.session_setup = setup['session']

        # Per ADC
        self.daq_setup = dict([(adc, self.irrad_setup['daq'][adc]) for adc in self.adc_names])
        self.channels = dict([(adc, self.daq_setup[adc]['channels']) for adc in self.adc_names])
        self.ch_type_idx = {}

        for adc in self.adc_names:
            self.ch_type_idx[adc] = dict([(x, self.daq_setup[adc]['types'].index(x))
                                          for x in roe_output if x in self.daq_setup[adc]['types']])

    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def _setup_interpreter(self):
        """Sets up the main zmq context and the sockets which are accessed within this process.
        This needs to be called within the run-method"""

        # Create main context for this process; sockets need to be created on their respective threads!
        self.context = zmq.Context()

        # Create PUB socket in order to send interpreted data
        self.data_pub = self.context.socket(zmq.PUB)
        self.data_pub.set_hwm(10)  # drop data if too slow
        self.data_pub.bind(self._tcp_addr(self.tcp_setup['port']['data']))

        # Start logging
        self._setup_logging()

        # Start daq
        self._setup_daq()

    def _setup_logging(self):
        """Setup logging"""

        # Numeric logging level
        numeric_level = getattr(logging, self.session_setup['loglevel'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: {}'.format(self.session_setup['loglevel']))

        # Set level
        logging.getLogger().setLevel(level=numeric_level)

        # Publish log
        log_pub = self.context.socket(zmq.PUB)
        log_pub.bind(self._tcp_addr(self.tcp_setup['port']['log']))

        # Create logging publisher first
        handler = handlers.PUBHandler(log_pub)
        logging.getLogger().addHandler(handler)

        time.sleep(2.5)

    def _setup_daq(self):

        # Data writing
        # One h5-file per ADC
        self.tables = {}

        # Store three tables per ADC
        self.raw_table = {}
        self.beam_table = {}
        self.fluence_table = {}
        self.result_table = {}
        self.offset_table = {}
        self.temp_table = {}

        # Store data per interpretation cycle and ADC
        self.raw_data = {}
        self.beam_data = {}
        self.fluence_data = {}
        self.result_data = {}
        self.auto_zero_offset = {}
        self._auto_zero_vals = {}
        self.temp_data = {}

        # Possible channels from which to get the beam positions
        self.pos_types = {'h': {'digital': ['sem_left', 'sem_right'], 'analog': ['sem_h_shift']},
                          'v': {'digital': ['sem_up', 'sem_down'], 'analog': ['sem_v_shift']}}

        # Possible channels from which to get the beam current
        self.current_types = {'digital': [('sem_left', 'sem_right'), ('sem_up', 'sem_down')], 'analog': 'sem_sum'}

        # Dtype for fluence data
        fluence_dtype = [('scan', '<i4'), ('row', '<i4'), ('current_mean', '<f4'), ('current_std', '<f4'),
                         ('current_err', '<f4'), ('speed', '<f4'), ('step', '<f4'), ('p_fluence', '<f8'),
                         ('p_fluence_err', '<f8'), ('timestamp_start', '<f8'), ('x_start', '<f4'), ('y_start', '<f4'),
                         ('timestamp_stop', '<f8'), ('x_stop', '<f4'), ('y_stop', '<f4')]

        result_dtype =  [('p_fluence_mean', '<f8'), ('p_fluence_err', '<f8'), ('p_fluence_std', '<f8')]

        # Dict with lists to append beam current values to during scanning
        self._beam_currents = defaultdict(list)

        # Current factor
        self.nA = 1e-9

        # Elementary charge
        self.qe = 1.60217733e-19

        # XY stage stuff
        self.n_rows = None
        self.y_step = None

        # Attributes indicating start and stop of stage
        self._stage_scanning = False
        self._store_fluence_data = False
        self._store_temp_data = False

        # Fluence
        self._fluence = {}
        self._fluence_err = {}

        # Open respective table files per ADC and check which data will be interpreted
        for adc in self.channels:

            # Make structured arrays for data organization when dropping to table
            raw_dtype = [('timestamp', '<f8')] + [(ch, '<f4') for ch in self.channels[adc]]
            beam_dtype = [('timestamp', '<f8')]
            temp_dtype = [('timestamp', '<f8')] + [(temp, '<f2') for temp in ('Temp. 0', 'Temp. 1')]

            # Check which data will be interpreted
            # Beam position
            for pos_type in self.pos_types:
                for sig in self.pos_types[pos_type]:
                    if all(t in self.ch_type_idx[adc] for t in self.pos_types[pos_type][sig]):
                        beam_dtype.append(('position_{}_{}'.format(pos_type, sig), '<f4'))

            # Beam current
            for curr_type in self.current_types:
                if curr_type == 'digital':
                    if any(all(s in self.ch_type_idx[adc] for s in t) for t in self.current_types[curr_type]):
                        beam_dtype.append(('current_{}'.format(curr_type), '<f4'))
                else:
                    if self.current_types[curr_type] in self.ch_type_idx[adc]:
                        beam_dtype.append(('current_{}'.format(curr_type), '<f4'))

            # Make arrays with given dtypes
            self.raw_data[adc] = np.zeros(shape=1, dtype=raw_dtype)
            self.beam_data[adc] = np.zeros(shape=1, dtype=beam_dtype)
            self.fluence_data[adc] = np.zeros(shape=1, dtype=fluence_dtype)
            self.result_data[adc] = np.zeros(shape=1, dtype=result_dtype)
            self.temp_data[adc] = np.zeros(shape=1, dtype=temp_dtype)

            # Auto zeroing offset
            self.auto_zero_offset[adc] = np.zeros(shape=1, dtype=raw_dtype)
            self._auto_zero_vals[adc] = defaultdict(list)

            # Open adc table
            self.tables[adc] = tb.open_file(self.session_setup['outfile'] + '_{}.h5'.format(adc), 'w')

            # Create data tables
            self.raw_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                description=self.raw_data[adc].dtype,
                                                                name='Raw')
            self.beam_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                 description=self.beam_data[adc].dtype,
                                                                 name='Beam')
            self.fluence_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                    description=self.fluence_data[adc].dtype,
                                                                    name='Fluence')
            self.result_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                   description=self.result_data[adc].dtype,
                                                                   name='Result')
            self.offset_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                   description=self.auto_zero_offset[adc].dtype,
                                                                   name='RawOffset')
            self.temp_table[adc] = self.tables[adc].create_table(self.tables[adc].root,
                                                                 description=self.temp_data[adc].dtype,
                                                                 name='Temperature')

    def interpret_data(self, raw_data):
        """Interpretation of the data"""

        # Retrive ADC name, meta data and actual data from raw data dict
        adc, meta_data, data = raw_data['meta']['name'], raw_data['meta'], raw_data['data']

        if meta_data['type'] == 'raw':

            ### Raw data ###

            # Get timestamp from data for beam and raw arrays
            self.raw_data[adc]['timestamp'] = self.beam_data[adc]['timestamp'] = meta_data['timestamp']

            # Fill raw data structured array first
            for ch in data:
                self.raw_data[adc][ch] = data[ch]
                # Subtract offset from data; initially offset is 0 for all ch
                data[ch] -= self.auto_zero_offset[adc][ch][0]

            # Get offsets
            if self.auto_zero.is_set():
                # Loop over data unitl sufficient data for mean is collected
                for ch in data:
                    self._auto_zero_vals[adc][ch].append(self.raw_data[adc][ch][0])
                    if len(self._auto_zero_vals[adc][ch]) == 40:
                        self.auto_zero_offset[adc][ch] = np.mean(self._auto_zero_vals[adc][ch])
                # If all offsets have been found, clear signal and reset list
                if all(len(self._auto_zero_vals[adc][ch]) >= 40 for ch in data):
                    self.auto_zero.clear()
                    self._auto_zero_vals[adc] = defaultdict(list)
                    self.auto_zero_offset[adc]['timestamp'] = time.time()
                    self.offset_table[adc].append(self.auto_zero_offset[adc])

            ### Interpretation of data ###

            # Beam data dict to publish to ZMQ in order to visualize
            beam_data = {'meta': {'timestamp': meta_data['timestamp'], 'name': adc, 'type': 'beam'},
                         'data': {'position': {'digital': {}, 'analog': {}}, 'current': {'digital': 0, 'analog': 0}}}

            # Loop over names in structured array which determine the data available
            for dname in self.beam_data[adc].dtype.names:

                # Extract the signal type from the dname; either analog or digital
                sig_type = dname.split('_')[-1]

                # Get beam position info of ADC
                if 'position' in dname:

                    # Extract position type which is either h or v for horizontal/vertical respectively
                    pos_type = dname.split('_')[1]

                    # Calculate shift from digitized signals of foils
                    if sig_type == 'digital':
                        # Digital shift is normalized; from -1 to 1
                        shift = self._calc_digital_shift(data, adc, self.pos_types[pos_type][sig_type], m=pos_type)

                    # Get shift from analog signal
                    else:
                        shift = data[self.channels[adc][self.ch_type_idx[adc][self.pos_types[pos_type][sig_type][0]]]]
                        shift *= 1. / 5.  # Analog shift from -5 to 5 V; divide by 5 V to normalize

                    # Shift to percent
                    shift *= 100.

                    # Write to dict to send out and to array to store
                    beam_data['data']['position'][sig_type][pos_type] = self.beam_data[adc][dname] = shift

                # Get beam current
                elif 'current' in dname:

                    # Calculate current from digitized signals of foils
                    if sig_type == 'digital':

                        # Get all channels present which represent individual foils
                        dig_chs = [ch for cch in self.current_types[sig_type]
                                   for ch in cch if ch in self.ch_type_idx[adc]]

                        # Number of foils
                        n_foils = len(dig_chs)

                        if n_foils not in (2, 4):
                            msg = "Digital current must be derived from 2 OR 4 foils, now it's {}".format(n_foils)
                            logging.warning(msg)

                        # Sum and divide by amount of foils
                        current = sum([data[self.channels[adc][self.ch_type_idx[adc][c]]] for c in dig_chs]) / n_foils

                    # Get current from analog signal
                    else:
                        current = data[self.channels[adc][self.ch_type_idx[adc][self.current_types[sig_type]]]]

                    # Up to here *current* is actually a voltage between 0 and 5 V which is now converted to nano ampere
                    current *= self.daq_setup[adc]['ro_scale'] * self.daq_setup[adc]['prop_constant'] * self.nA

                    # Write to dict to send out and to array to store
                    beam_data['data']['current'][sig_type] = self.beam_data[adc][dname] = current

            self.data_pub.send_json(beam_data)

        elif meta_data['type'] == 'temp':

            self.temp_data[adc]['timestamp'] = meta_data['timestamp']
            for temp in data:
                self.temp_data[adc][temp] = data[temp]

            self._store_temp_data = True

        elif meta_data['type'] == 'stage':

            if data['status'] == 'init':
                self.y_step = data['y_step']
                self.n_rows = data['n_rows']
                self._fluence[adc] = [0] * self.n_rows
                self._fluence_err[adc] = [0] * self.n_rows

            elif data['status'] == 'start':
                del self._beam_currents[adc][:]
                self._stage_scanning = True
                self.fluence_data[adc]['timestamp_start'] = meta_data['timestamp']

                for prop in ('scan', 'row', 'speed', 'x_start', 'y_start'):
                    self.fluence_data[adc][prop] = data[prop]

            elif data['status'] == 'stop':
                self._stage_scanning = False
                self.fluence_data[adc]['timestamp_stop'] = meta_data['timestamp']

                for prop in ('x_stop', 'y_stop'):
                    self.fluence_data[adc][prop] = data[prop]

                # Do fluence calculation
                # Mean current over scanning time
                mean_current, std_current = np.mean(self._beam_currents[adc]), np.std(self._beam_currents[adc])

                # Error on current measurement is Delta I = 3.3% I + 1% R_FS
                actual_current_error = 0.033 * mean_current + 0.01 * self.daq_setup[adc]['ro_scale'] * self.nA

                # Quadratically add the measurement error and beam current fluctuation
                p_f_err = np.sqrt(std_current**2. + actual_current_error**2.)

                # Fluence and its error; speed and step_size are in mm; factor 1e-2 to convert to cm^2
                p_fluence = mean_current / (self.y_step * self.fluence_data[adc]['speed'][0] * self.qe * 1e-2)
                p_fluence_err = p_f_err / (self.y_step * self.fluence_data[adc]['speed'][0] * self.qe * 1e-2)

                # Write to array
                self.fluence_data[adc]['current_mean'] = mean_current
                self.fluence_data[adc]['current_std'] = std_current
                self.fluence_data[adc]['current_err'] = actual_current_error
                self.fluence_data[adc]['p_fluence'] = p_fluence
                self.fluence_data[adc]['p_fluence_err'] = p_fluence_err
                self.fluence_data[adc]['step'] = self.y_step

                # User feedback
                logging.info('Fluence row {}: ({:.2E} +- {:.2E}) protons / cm^2'.format(self.fluence_data[adc]['row'][0],
                                                                                        p_fluence, p_fluence_err))

                # Add to overall fluence
                self._fluence[adc][self.fluence_data[adc]['row'][0]] += self.fluence_data[adc]['p_fluence'][0]

                # Update the error a la Gaussian error propagation
                old_fluence_err = self._fluence_err[adc][self.fluence_data[adc]['row'][0]]
                current_fluence_err = self.fluence_data[adc]['p_fluence_err'][0]
                new_fluence_err = np.sqrt(old_fluence_err**2.0 + current_fluence_err**2.0)

                # Update
                self._fluence_err[adc][self.fluence_data[adc]['row'][0]] = new_fluence_err

                fluence_data = {'meta': {'timestamp': meta_data['timestamp'], 'name': adc, 'type': 'fluence'},
                                'data': {'hist': self._fluence[adc], 'hist_err': self._fluence_err[adc]}}

                self._store_fluence_data = True

                self.data_pub.send_json(fluence_data)

                self._update_xy_stage_stats(adc)

            elif data['status'] == 'finished':

                # The stage is finished; append the overall fluence to the result and get the sigma by the std dev
                self.result_data[adc]['p_fluence_mean'] = np.mean(self._fluence[adc])
                self.result_data[adc]['p_fluence_err'] = np.sqrt(np.sum(np.power(np.array(self._fluence_err[adc]) / len(self._fluence[adc]), 2.)))
                self.result_data[adc]['p_fluence_std'] = np.std(self._fluence[adc])
                self.result_table[adc].append(self.result_data[adc])

                # Write everything to the file
                self.tables[adc].flush()

        # During scan, store all beam currents in order to get mean current over scanned row
        if self._stage_scanning:
            self._beam_currents[adc].append(self.beam_data[adc]['current_analog'][0])

    def _update_xy_stage_stats(self, adc):

        # Add to xy stage stats
        # This iterations travel
        x_travel = float(abs(self.fluence_data[adc]['x_stop'][0] - self.fluence_data[adc]['x_start'][0]))
        y_travel = float(self.fluence_data[adc]['step'][0] * 1e-3)

        # Add to total
        self.stage_stats['total_travel']['x'] += x_travel
        self.stage_stats['total_travel']['y'] += y_travel

        # Add to interval
        self.stage_stats['interval_travel']['x'] += x_travel
        self.stage_stats['interval_travel']['y'] += y_travel

        # Check if any axis has reached interval travel
        for axis in ('x', 'y'):
            if self.stage_stats['interval_travel'][axis] > self.stage_stats['maintenance_interval']:
                self.stage_stats['interval_travel'][axis] = 0.0
                self.xy_stage_maintenance.set()
                logging.warning("{}-axis of XY-stage reached service interval travel! "
                                "See https://www.zaber.com/wiki/Manuals/X-LRQ-E#Precautions".format(axis))

        self.stage_stats['last_update'] = time.asctime()

    def _calc_digital_shift(self, data, adc, ch_types, m='h'):
        """Calculate the beam displacement on the secondary electron monitor from the digitized foil signals"""

        # Get indices of respective foil signals in data and extract
        idx_a, idx_b = self.ch_type_idx[adc][ch_types[0]], self.ch_type_idx[adc][ch_types[1]]
        a, b = data[self.channels[adc][idx_a]], data[self.channels[adc][idx_b]]

        # Do calc and catch ZeroDivisionError
        try:
            res = (a - b) / (a + b)
        except ZeroDivisionError:
            res = None

        # Horizontally, if we are shifted to the left the graph should move to the left, therefore * -1
        return res if res is None else -1 * res if m == 'h' else res

    def store_data(self):
        """Method which appends current data to table files. If tables are longer then self._max_buf_len,
        flush the buffer to hard drive"""

        # Loop over tables and append the data
        for adc in self.tables:
            self.raw_table[adc].append(self.raw_data[adc])
            self.beam_table[adc].append(self.beam_data[adc])

            # If the stage scanned, append data
            if self._store_fluence_data:
                self.fluence_table[adc].append(self.fluence_data[adc])
                self._store_fluence_data = False

            if self._store_temp_data:
                self.temp_table[adc].append(self.temp_data[adc])
                self._store_temp_data = False

            # If tables are getting too large, flush buffer to hard drive
            if any(t[adc].nrows % self._max_buf_len == 0 and t[adc].nrows != 0 for t in (self.raw_table,
                                                                                         self.beam_table,
                                                                                         self.fluence_table)):
                self.tables[adc].flush()

    def recv_data(self):
        """Main method which receives raw data and calls interpretation and data storage methods"""

        # Create subscriber for raw and XY-Stage data
        data_sub = self.context.socket(zmq.SUB)
        for port in ('data', 'stage', 'temp'):
            data_sub.connect(self._tcp_addr(self.tcp_setup['port'][port], ip=self.tcp_setup['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')

        # Set signal for main to proceed
        self.is_receiving.set()

        # While event not set receive data with 1 ms wait
        while not self.stop_recv_data.wait(1e-3):

            # Try getting data without blocking. If no data exception is raised.
            try:
                # Get data
                data = data_sub.recv_json(flags=zmq.NOBLOCK)

                # Interpret data
                self.interpret_data(data)

                # If event is not set, store data to hdf5 file
                if not self.stop_write_data.wait(1e-3):
                    self.store_data()

            # No data
            except zmq.Again:
                pass

    def shutdown(self):
        """Set events in order to leave receiver loop and end process"""

        # User info
        logging.info('Shutting down {}...'.format(self.name.capitalize()))

        # Setting signals to stop
        self.stop_write_data.set()
        self.stop_recv_data.set()

    def _close_tables(self):
        """Method to close the h5-files which were opened in the setup_daq method"""

        # User info
        logging.info('Closing data files {}'.format(', '.join(self.tables[adc].filename for adc in self.tables)))

        # Loop over all ADCs and close
        for adc in self.tables:
            self.tables[adc].close()

    def run(self):
        """This will be run in a dedicated process on calling the Process.start() method"""

        # Setup interpreters zmq connections and logging and daq
        self._setup_interpreter()

        # User info
        logging.info('Starting {}'.format(self.name))

        try:

            # Main process runs command receive loop
            self.recv_data()

        except Exception:
            logging.exception("Unexpected exception occured.")
            pass

        # Make sure we're closing the data tables
        finally:

            # Close opened data files
            self._close_tables()

            # Overwrite xy stage stats
            with open(os.path.join(config_path, 'xy_stage_stats.yaml'), 'w') as _xys:
                yaml.safe_dump(self.stage_stats, _xys, default_flow_style=False)

            # User info
            logging.info('{} finished'.format(self.name.capitalize()))
