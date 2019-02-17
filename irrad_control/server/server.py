import zmq
import sys
import time
import multiprocessing
import threading
import logging
from zmq.log import handlers
from adc.ADS1256_definitions import *
from adc.ADS1256_drates import ads1256_drates
from adc.pipyadc import ADS1256


class IrradServer(multiprocessing.Process):
    """Implements a server process which controls the DAQ and XYStage"""

    def __init__(self, cmd_port):
        super(IrradServer, self).__init__()

        # Attributes for internal handling of sending data, receiving and commands
        self._send_data = True
        self._recv_cmds = True
        self._busy_cmd = False

        # Command port to bind to
        self.cmd_port = cmd_port

        # Init zmq related attributes
        self.server_rep = None
        self.context = None

        # Attribute to hold beam current; needed for XY-Stage as scan criteria
        self.beam_current = None

        # Minimum beam current
        self.min_beam_current = None
        
        # Dict of known commands
        self.commands = {'server': ['start', 'set_current', 'set_min_current'], 'adc': [], 'stage': []}

        # Attribute to store setup in
        self.irrad_setup = None
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def _setup_logging(self):
        """Setup logging"""

        # Numeric logging level
        numeric_level = getattr(logging, self.irrad_setup['session']['loglevel'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: {}'.format(self.irrad_setup['session']['loglevel']))

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
        
    def _setup_adc(self):
        """Setup the ADS1256 instance and channels"""

        # Instance of ADS1256 ADC on WaveShare board
        self.adc = ADS1256()

        # Set initial data rate from DAQ setup
        self.adc.drate = ads1256_drates[self.daq_setup['sampling_rate']]
        
        # Calibrate the ADC before DAQ
        self.adc.cal_self()
    
        # Declare all available channels of the ADS1256
        self._pos_channels = (POS_AIN0, POS_AIN1, POS_AIN2, POS_AIN3, POS_AIN4, POS_AIN5, POS_AIN6, POS_AIN7)
        self._gnd = NEG_AINCOM
        self.adc_channels = []

        # Assign the physical channel numbers e.g. multiplexer address
        for ch in self.daq_setup['ch_numbers']:
            # Single-ended versus common ground self._gnd
            if isinstance(ch, int):
                tmp_ch = self._pos_channels[ch] | self._gnd
            # Differential measurement
            else:
                a, b = ch
                tmp_ch = self._pos_channels[a] | self._pos_channels[b]
            # Add to channels
            self.adc_channels.append(tmp_ch)

    def _start_server(self, irrad_setup):
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
        data_thread = threading.Thread(target=self.send_data)
        data_thread.start()

    def send_data(self):
        """Sends data from dedicated thread"""

        # Needs to be specified within this func since its run on dedicated thread
        data_pub = self.context.socket(zmq.PUB)
        data_pub.set_hwm(10)  # drop data if too slow
        data_pub.bind(self._tcp_addr(self.tcp_setup['port']['data']))

        # Send data als long as specified
        while self._send_data:

            # Read raw data from ADC
            raw_data = self.adc.read_sequence(self.adc_channels)

            # Add meta data
            _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'raw'}
            _data = dict([(self.daq_setup['channels'][i], raw_data[i] * self.adc.v_per_digit) for i in range(len(raw_data))])

            # Send
            data_pub.send_json({'meta': _meta, 'data': _data})

    def _send_reply(self, reply, _type, sender, data=None):

        reply_dict = {'reply': reply, 'type': _type, 'sender': sender}

        if data is not None:
            reply_dict['data'] = data

        self.server_rep.send_json(reply_dict)
        
    def recv_cmd(self):
        """Receiving commands at self.cmd_port.
        This is the main function which will be executed within the run-method"""

        # Create server socket and bind to cmd port
        self.server_rep = self.context.socket(zmq.REP)
        self.server_rep.bind(self._tcp_addr(self.cmd_port))

        # Receive commands as long as self._recv_cmds is True
        while self._recv_cmds:

            # Check if were working on a command. We have to work sequentially
            if not self._busy_cmd:

                # Cmd must be dict with command as 'cmd' key and 'args', 'kwargs' keys
                cmd_dict = self.server_rep.recv_json()

                # Set cmd to busy; other commands send will be queued and received later
                self._busy_cmd = True

                # Extract info from cmd_dict
                target = cmd_dict['target']
                cmd = cmd_dict['cmd']
                cmd_data = None if 'data' not in cmd_dict else cmd_dict['data']

                # Containers for errors
                error_reply = False

                # Command sanity checks
                if target not in self.commands:
                    msg = "Target '{}' unknown. Known targets are {}!".format(', '.join(self.commands.keys()), target)
                    logging.error(msg)
                    error_reply = 'No server target named {}'.format(target)

                elif cmd not in self.commands[target]:
                    msg = "Target command '{}' unknown. Known commands are {}!".format(', '.join(self.commands[target]),
                                                                                       cmd)
                    logging.error(msg)
                    error_reply = 'No target command named {}'.format(cmd)

                # Check for errors
                if error_reply:
                    self._send_reply(reply=error_reply, sender='server', _type='ERROR', data=None)
                    self._busy_cmd = False
                else:
                    self.handle_cmd(target=target, cmd=cmd, cmd_data=cmd_data)

    def handle_cmd(self, target, cmd, cmd_data):
        """Handle all commands. After every command a reply must be send."""

        # Handle server commands
        if target == 'server':

            if cmd == 'start':

                # Start server with setup which is cmd data
                self._start_server(cmd_data)

                # Send reply which is PID of this process
                self._send_reply(reply='pid', data=self.ident, sender='server', _type='STANDARD')

            if cmd == 'set_current':
                self.beam_current = cmd_data

                self._send_reply(reply='current', _type='STANDARD', sender='server', data=self.beam_current)

            if cmd == 'set_min_current':
                self.min_beam_current = cmd_data

                self._send_reply(reply='min_current', _type='STANDARD', sender='server', data=self.min_beam_current)

        # Set busy False after executed cmd
        self._busy_cmd = False

    def run(self):

        # Create context; needs to be within run(); sockets have to be created within the respective thread
        self.context = zmq.Context()
        
        # Main process runs command receive loop
        self.recv_cmd()


if __name__ == '__main__':
    
    port = sys.argv[1]
    irrad_server = IrradServer(port)
    irrad_server.start()
