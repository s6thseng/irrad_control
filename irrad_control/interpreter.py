import zmq
import time
import multiprocessing
import logging
import psutil
from zmq.log import handlers


class IrradInterpreter(multiprocessing.Process):
    """Implements a server process which controls the DAQ and XYStage"""

    def __init__(self, irrad_setup, name=None):
        super(IrradInterpreter, self).__init__()

        self.name = 'interpreter' if name is None else name

        # Attribute to store setup in
        self.irrad_setup = irrad_setup
        self.tcp_setup = irrad_setup['tcp']

        # Attributes to handle sending / receiving and handling commands
        self._send_data = True
        self._recv_data = True
        self._recv_cmds = True
        self._busy_cmd = False

        # Dict of existing commands
        self.commands = {}

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

    def recv_data(self):
        """Method that is run on different thread which receives raw data and calls interpretation method"""

        # Create subscriber for raw and XY-Stage data
        data_sub = self.context.socket(zmq.SUB)
        data_sub.connect(self._tcp_addr(self.tcp_setup['port']['data'], ip=self.tcp_setup['ip']['server']))
        data_sub.setsockopt(zmq.SUBSCRIBE, '')

        while self._recv_data:

            data = data_sub.recv_json()
            self.interpret_data(data)

    def interpret_data(self, data):
        adc = data['meta']['name']

        # Send data
        current = {'analog': 0.770 * self.irrad_setup['daq'][adc]['ro_scale'] * data['data'][self.irrad_setup['daq'][adc]['channels'][4]]}

        self.data_pub.send_json({'meta': {'timestamp': data['meta']['timestamp'], 'type': 'beam', 'name': adc}, 'data': {'current': current}})

    def run(self):

        # Process info
        self.process = psutil.Process(self.ident)

        # Setup interpreters zmq connections and logging
        self._setup_interpreter()

        # Main process runs command receive loop
        self.recv_data()
