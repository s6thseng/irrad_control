import zmq
import sys
import time
import multiprocessing
import threading
import logging
import psutil
from collections import OrderedDict
from zmq.log import handlers
from adc.ADS1256_definitions import *
from adc.pipyadc import ADS1256


# ADS1256 data rates and number of averages per data rate
ads1256 = OrderedDict()

# Data rate in samples per second
ads1256_drates = OrderedDict([(30000, DRATE_30000), (15000, DRATE_15000), (7500, DRATE_7500), (3750, DRATE_3750),
                              (2000, DRATE_2000), (1000, DRATE_1000), (500, DRATE_500), (100, DRATE_100),
                              (60, DRATE_60), (50, DRATE_50), (30, DRATE_30), (25, DRATE_25),
                              (15, DRATE_15), (10, DRATE_10), (5, DRATE_5), (2.5, DRATE_2_5)])


class IrradServer(multiprocessing.Process):
    """Implements a server process which controls the DAQ and XYStage"""

    def __init__(self, cmd_port):
        super(IrradServer, self).__init__()
        
        # Process info
        self.process = psutil.Process(self.ident)

        # Attributes to handle sending data, receiving and handling commands
        self.send_data = True
        self.recv_cmds = True
        self.busy_cmd = False

        # Command port to bind to
        self.cmd_port = cmd_port

        # Init zmq related attributes
        self.server_rep = None
        self.context = None
        
        # List of known commands
        self.cmds = ['setup_server']

        # Attribute to store setup in
        self.irrad_setup = None
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)
        
    def _setup_server(self, irrad_setup):
        """Sets up the server process"""

        # Update setup
        self.irrad_setup = irrad_setup

        # Extract info and sub setups
        self.adc_name = irrad_setup['daq'].keys()[0]
        self.daq_setup = irrad_setup['daq'][self.adc_name]
        self.tcp_setup = irrad_setup['tcp']
        
        # Setup logging
        self._setup_logging()
        
        # Setup adc
        self._setup_adc()

        # Start data sending thread
        data_thread = threading.Thread(target=self.output_data)
        data_thread.start()

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
        
    def _setup_adc(self):
        """Setup the ADS1256 instance and channels"""
        
        self.adc = ADS1256()
        self.adc.drate = ads1256_drates[self.daq_setup['sampling_rate']]
        
        # self-calibration
        self.adc.cal_self()
    
        # channels TODO: represent not only positive channels
        self._all_channels = [ch_i | NEG_AINCOM for ch_i in (POS_AIN0, POS_AIN1, POS_AIN2, POS_AIN3,
                                                             POS_AIN4, POS_AIN5, POS_AIN6, POS_AIN7)]
        
        self.adc_channels = [self._all_channels[i] for i in self.daq_setup['ch_numbers']]
        
    def recv_cmd(self):
        """Receiving commands at self._cmd_port"""

        # Receive commands as long as self.recv_cmds is True
        while self.recv_cmds:

            if not self.busy_cmd:
                # Cmd must be dict with command as 'cmd' key and 'args', 'kwargs' keys
                cmd_dict = self.server_rep.recv_json()

                # Set cmd to busy; other commands send will be queued and received later
                self.busy_cmd = True

                if 'cmd' not in cmd_dict:
                    logging.error("Command must be dictionary with actual command in cmd_dict['cmd']!")
                    self.server_rep.send_json({'reply': 'Error', 'sender': 'server'})
                    self.busy_cmd = False
                    continue
                elif cmd_dict['cmd'] not in self.cmds:
                    logging.error("Command {} not listed in commands: {}".format(cmd_dict['cmd'],
                                                                                 ', '.join(str(x) for x in self.cmds)))
                    self.server_rep.send_json({'reply': 'Error', 'sender': 'server'})
                    self.busy_cmd = False
                    continue

                self.handle_cmd(cmd_dict)
        
    def output_data(self):
        """Sends data from dedicated thread"""

        # Needs to be specified within this func since its run on dedicated thread
        data_pub = self.context.socket(zmq.PUB)
        data_pub.set_hwm(10)  # drop data if too slow
        data_pub.bind(self._tcp_addr(self.tcp_setup['port']['data']))

        # Send data als long as specified
        while self.send_data:

            # Read raw data from ADC
            raw_data = self.adc.read_sequence(self.adc_channels)

            # Add meta data
            _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'raw'}
            _data = dict([(self.daq_setup['channels'][i], raw_data[i] * self.adc.v_per_digit) for i in range(len(raw_data))])

            # Send
            data_pub.send_json({'meta': _meta, 'data': _data})

    def handle_cmd(self, cmd_dict):
        """Handle all commands. After every command a reply must be send."""

        cmd = cmd_dict['cmd']
        cmd_data = None if 'data' not in cmd_dict else cmd_dict['data']

        if cmd == 'setup_server':
            self._setup_server(cmd_data)
            self.server_rep.send_json({'reply': 'server_pid', 'data': self.ident, 'sender': 'server'})

        if cmd == 'herro':
            self.server_rep.send_json({'reply': 'Herro', 'sender': 'server'})

        # Set busy False after executed cmd
        self.busy_cmd = False

    def run(self):
        # Create context; thread safe, sockets though have to be created within the respective thread
        self.context = zmq.Context()

        # Create server socket and bind to cmd port
        self.server_rep = self.context.socket(zmq.REP)
        self.server_rep.bind(self._tcp_addr(self.cmd_port))
        
        # Main process runs command receive loop
        self.recv_cmd()


if __name__ == '__main__':
    
    port = sys.argv[1]
    irrad_server = IrradServer(port)
    irrad_server.start()
