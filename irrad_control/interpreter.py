import zmq
import time
import multiprocessing
import logging
import numpy as np
import tables as tb
from zmq.log import handlers
from irrad_control import roe_output


class IrradInterpreter(multiprocessing.Process):
    """Implements an interpreter process"""

    def __init__(self, name=None):
        super(IrradInterpreter, self).__init__()

        """
        IMPORTANT:
        The attributes initialized in here are only available as COPIES in the run()-method.
        In order to change attributes during runtime use multiprocessing.Event objects or queues. 
        """

        self.name = 'interpreter' if name is None else name

        # Attributes to interact with the actual process stuff running within run()
        self.stop_recv_data = multiprocessing.Event()
        self.stop_write_data = multiprocessing.Event()

    def _init_setup(self, setup):

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
        logging.basicConfig(level=numeric_level)

        # Publish log
        log_pub = self.context.socket(zmq.PUB)
        log_pub.bind(self._tcp_addr(self.tcp_setup['port']['log']))

        # Create logging publisher first
        handler = handlers.PUBHandler(log_pub)
        logging.getLogger().addHandler(handler)

        # Allow connections to be made
        time.sleep(1)

    def _setup_daq(self):

        # Data writing
        self.tables = {}
        self.raw_table = {}
        self.beam_table = {}
        self.fluence_table = {}
        self.raw_data = {}
        self.beam_data = {}
        self.fluence_data = {}

        # Possible channels from which to get the beam positions
        pos_types = {'h': {'digital': ['sem_left', 'sem_right'], 'analog': ['sem_h_shift']},
                     'v': {'digital': ['sem_up', 'sem_down'], 'analog': ['sem_v_shift']}}

        # Possible channels from which to get the beam current
        current_types = {'digital': [('sem_left', 'sem_right'), ('sem_up', 'sem_down')], 'analog': 'sem_sum'}

        # Dtype for fluence data
        fluence_dtype = [('scan', '<i4'), ('row', '<i4'), ('current', '<f4'), ('pfluence', '<f8'), ('nfluence', '<f8'),
                         ('timestamp_start', '<f4'), ('x_start', '<f4'), ('y_start', '<f4'),
                         ('timestamp_stop', '<f4'), ('x_stop', '<f4'), ('y_stop', '<f4')]

        # Open respective table files per ADC and check which data will be interpreted
        for adc in self.channels:

            # Make structured arrays for data organization when dropping to table
            raw_dtype = [('timestamp', '<f8')] + [(ch, '<f4') for ch in self.channels[adc]]
            beam_dtype = [('timestamp', '<f8')]

            # Check which data will be interpreted
            # Beam position
            for pos_type in pos_types:
                for sig in pos_types[pos_type]:
                    if all(t in self.ch_type_idx[adc] for t in pos_types[pos_type][sig]):
                        beam_dtype.append(('position_{}_{}'.format(pos_type, sig), '<f4'))

            # Beam current
            for curr_type in current_types:
                if curr_type == 'digital':
                    if any(all(s in self.ch_type_idx[adc] for s in t) for t in current_types[curr_type]):
                        beam_dtype.append(('current_{}'.format(curr_type), '<f4'))
                else:
                    if current_types[curr_type] in self.ch_type_idx[adc]:
                        beam_dtype.append(('current_{}'.format(curr_type), '<f4'))

            # Make arrays with given dtypes
            self.raw_data[adc] = np.zeros(shape=1, dtype=raw_dtype)
            self.beam_data[adc] = np.zeros(shape=1, dtype=beam_dtype)
            self.fluence_data[adc] = np.zeros(shape=1, dtype=fluence_dtype)

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

    def interpret_data(self, raw_data):
        """Interpretation of the data"""

        adc, meta_data, data = raw_data['meta']['name'], raw_data['meta'], raw_data['data']

        if not self.stop_write_data.is_set():
            self.raw_data[adc]['timestamp'] = meta_data['timestamp']
            for ch in data:
                self.raw_data[adc][ch] = data[ch]
            self.raw_table[adc].append(self.raw_data[adc])

        # Beam position
        pos_data = {'digital': {}, 'analog': {}}

        pos_types = {'h': {'digital': ['sem_left', 'sem_right'], 'analog': ['sem_h_shift']},
                     'v': {'digital': ['sem_up', 'sem_down'], 'analog': ['sem_v_shift']}}

        # Check which channel types are present from which the beam position can be calculated
        for pos_type in pos_types:
            for sig in pos_types[pos_type]:
                if all(t in self.ch_type_idx[adc] for t in pos_types[pos_type][sig]):
                    if sig == 'digital':
                        shift = self._calc_digital_shift(data, adc, pos_types[pos_type][sig], m=pos_type)
                    else:
                        shift = data[self.channels[adc][self.ch_type_idx[adc][pos_types[pos_type][sig][0]]]]
                    pos_data[sig][pos_type] = shift

        # Beam current
        current_data = {'digital': 0, 'analog': 0}

        # From the digital signal of the SEM foils
        tmp_dig_vals = []
        for current_type in [('sem_left', 'sem_right'), ('sem_up', 'sem_down')]:
            if all(t in self.ch_type_idx[adc] for t in current_type):
                tmp_dig_vals += [data[self.channels[adc][self.ch_type_idx[adc][c]]] for c in current_type]

        current_data['digital'] += sum([val / float(len(tmp_dig_vals)) for val in tmp_dig_vals])

        # From the analog sum signal of all SEM foils
        if 'sem_sum' in self.ch_type_idx[adc]:
            current_data['analog'] = data[self.channels[adc][self.ch_type_idx[adc]['sem_sum']]]

        # Scale to real beam current via proportionality constant and RO scale
        for v in current_data:
            current_data[v] *= self.daq_setup[adc]['ro_scale'] * self.daq_setup[adc]['prop_constant'] * 1e-9

        # Publish data
        beam_data = {'meta': {'timestamp': time.time(), 'name': adc, 'type': 'beam'},
                     'data': {'position': pos_data, 'current': current_data}}

        self.data_pub.send_json(beam_data)

    def _calc_digital_shift(self, data, adc, ch_types, m='h'):

        idx_a, idx_b = self.ch_type_idx[adc][ch_types[0]], self.ch_type_idx[adc][ch_types[1]]
        a, b = data[self.channels[adc][idx_a]], data[self.channels[adc][idx_b]]

        try:
            res = (a - b) / (a + b)
        except ZeroDivisionError:
            res = None

        # Horizontally, if we are shifted to the left the graph should move to the left, therefore * -1
        return res if res is None else -1 * res if m == 'h' else res

    def recv_data(self):
        """Method that is run on different thread which receives raw data and calls interpretation method"""

        # Create subscriber for raw and XY-Stage data
        data_sub = self.context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.tcp_setup['port']['data'], ip=self.tcp_setup['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')

        while not self.stop_recv_data.wait(0.001):
            try:
                data = data_sub.recv_json(flags=zmq.NOBLOCK)
                self.interpret_data(data)
            except zmq.Again:  # no data
                pass

    def shutdown(self):
        self.stop_recv_data.set()

    def _close_tables(self):
        for adc in self.tables:
            self.tables[adc].close()

    def run(self):

        # Setup interpreters zmq connections and logging and daq
        self._setup_interpreter()

        logging.info('Starting {}'.format(self.name))

        # Main process runs command receive loop
        self.recv_data()

        # Close opened data tables
        self._close_tables()

        logging.info('{} finished'.format(self.name))
