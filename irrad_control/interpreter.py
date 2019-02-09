import zmq
import time
import multiprocessing
import logging
import psutil
from zmq.log import handlers
from irrad_control import roe_output


class IrradInterpreter(multiprocessing.Process):
    """Implements an interpreter process"""

    def __init__(self, name=None):
        super(IrradInterpreter, self).__init__()

        self.name = 'interpreter' if name is None else name

        # Attribute to store setup in
        self.irrad_setup = None
        self.tcp_setup = None
        self.adc_names = None
        self.daq_setup = None

        # Attributes to handle sending / receiving and handling commands
        self._send_data = True
        self._recv_data = True
        self._recv_cmds = True
        self._busy_cmd = False

        # Attributes for zmq
        self.context = None
        self.data_pub = None

        # Process info
        self.process = psutil.Process(self.ident)

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

    def _setup_logging(self):
        """Setup logging"""

        # Numeric logging level
        numeric_level = getattr(logging, self.irrad_setup['log']['level'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: {}'.format(self.irrad_setup['log']['level']))

        # Set level
        logging.basicConfig(level=numeric_level)

        # Publish log
        log_pub = self.context.socket(zmq.PUB)
        log_pub.bind(self._tcp_addr(self.tcp_setup['port']['log']))

        # Create logging publisher first
        handler = handlers.PUBHandler(log_pub)
        logging.getLogger().addHandler(handler)

    def update_setup(self, setup):

        # General setup
        self.irrad_setup = setup
        self.tcp_setup = setup['tcp']
        self.adc_names = setup['daq'].keys()

        # Per ADC
        self.daq_setup = dict([(adc, self.irrad_setup['daq'][adc]) for adc in self.adc_names])
        self.channels = dict([(adc, self.daq_setup[adc]['channels']) for adc in self.adc_names])
        self.ch_type_idx = {}

        for adc in self.adc_names:
            self.ch_type_idx[adc] = dict([(x, self.daq_setup[adc]['types'].index(x))
                                          for x in roe_output if x in self.daq_setup[adc]['types']])

    def recv_data(self):
        """Method that is run on different thread which receives raw data and calls interpretation method"""

        # Create subscriber for raw and XY-Stage data
        data_sub = self.context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.tcp_setup['port']['data'], ip=self.tcp_setup['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')

        while self._recv_data:
            data = data_sub.recv_json()
            self.interpret_data(data)

    def interpret_data(self, raw_data):
        """Interpretation of the data"""

        adc, meta_data, data = raw_data['meta']['name'], raw_data['meta'], raw_data['data']

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

        for current_type in [('sem_left', 'sem_right'), ('sem_up', 'sem_down')]:
            if all(t in self.ch_type_idx[adc] for t in current_type):
                tmp_vals = [data[self.channels[adc][self.ch_type_idx[adc][c]]] / 2. for c in current_type]
                current_data['digital'] += sum(tmp_vals)

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

    def run(self):

        # Setup interpreters zmq connections and logging
        self._setup_interpreter()

        # Main process runs command receive loop
        self.recv_data()
