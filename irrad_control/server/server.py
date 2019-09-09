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
from xystage import ZaberXYStage
from arduino_temp_sens import ArduinoTempSens


class IrradServer(multiprocessing.Process):
    """Implements a server process which controls the DAQ and XYStage"""

    def __init__(self, cmd_port):
        super(IrradServer, self).__init__()

        # Attributes for internal handling of sending data, receiving and commands
        self.stop_send_data = threading.Event()
        self.stop_send_temp = threading.Event()
        self.stop_recv_cmds = multiprocessing.Event()
        self._busy_cmd = False

        # Command port to bind to
        self.cmd_port = cmd_port

        # Init zmq related attributes
        self.server_rep = None
        self.context = None

        # Dict of known commands
        self.commands = {'adc': [],
                         'server': ['start', 'shutdown'],
                         'stage': ['move_rel', 'move_abs', 'prepare', 'scan', 'finish', 'stop', 'pos', 'home',
                                   'set_speed', 'get_speed', 'no_beam']
                         }

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

        # Init stage
        #self.xy_stage = ZaberXYStage()

        # Init temp sens
        self.temp_sens = ArduinoTempSens()

        # Start data sending thread
        temp_thread = threading.Thread(target=self.send_temp)
        temp_thread.start()

    def send_data(self):
        """Sends data from dedicated thread"""

        # Needs to be specified within this func since its run on dedicated thread
        data_pub = self.context.socket(zmq.PUB)
        data_pub.set_hwm(10)  # drop data if too slow
        data_pub.bind(self._tcp_addr(self.tcp_setup['port']['data']))

        # Send data als long as specified
        while not self.stop_send_data.is_set():
            # Read raw data from ADC
            raw_data = self.adc.read_sequence(self.adc_channels)

            # Add meta data
            _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'raw'}
            _data = dict(
                [(self.daq_setup['channels'][i], raw_data[i] * self.adc.v_per_digit) for i in range(len(raw_data))])

            # Send
            data_pub.send_json({'meta': _meta, 'data': _data})

    def send_temp(self):
        """Sends temp data from dedicated thread"""

        # Needs to be specified within this func since its run on dedicated thread
        temp_pub = self.context.socket(zmq.PUB)
        temp_pub.set_hwm(10)  # drop data if too slow
        temp_pub.bind(self._tcp_addr(self.tcp_setup['port']['temp']))

        # Send data als long as specified
        while not self.stop_send_temp.is_set():
            # Read raw temp data
            raw_temp = self.temp_sens.get_temp([0, 2])

            _data = {'Temp. 0': raw_temp[0], 'Temp. 1': raw_temp[2]}

            # Add meta data
            _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'temp'}
            # Send
            temp_pub.send_json({'meta': _meta, 'data': _data})

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

        # Receive commands as long as self.stop_recv_cmds is not set
        while not self.stop_recv_cmds.is_set():

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
                    msg = "Target '{}' unknown. Known targets are {}!".format(target, ', '.join(self.commands.keys()))
                    logging.error(msg)
                    error_reply = 'No server target named {}'.format(target)

                elif cmd not in self.commands[target]:
                    msg = "Target command '{}' unknown. Known commands are {}!".format(cmd,
                                                                                       ', '.join(self.commands[target]))
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

            elif cmd == 'shutdown':
                self._send_reply(reply='shutdown', _type='STANDARD', sender='server')
                self.stop_send_data.set()
                self.stop_recv_cmds.set()

        elif target == 'stage':

            if cmd == 'move_rel':
                axis = cmd_data['axis']
                _data = None
                if axis == 'x':
                    self.xy_stage.move_horizontal(cmd_data['distance'], unit=cmd_data['unit'])
                    _data = self.xy_stage.microstep * self.xy_stage.x_axis.get_position()
                elif axis == 'y':
                    self.xy_stage.move_vertical(cmd_data['distance'], unit=cmd_data['unit'])
                    _data = self.xy_stage.microstep * self.xy_stage.y_axis.get_position()

                self._send_reply(reply='move_rel', _type='STANDARD', sender='stage', data=_data)

            elif cmd == 'move_abs':
                axis = cmd_data['axis']
                _data = None
                dist_steps = self.xy_stage.distance_to_steps(cmd_data['distance'], unit=cmd_data['unit'])
                if axis == 'x':
                    self.xy_stage.x_axis.move_abs(dist_steps)
                    _data = self.xy_stage.microstep * self.xy_stage.x_axis.get_position()
                elif axis == 'y':
                    self.xy_stage.y_axis.move_abs(dist_steps)
                    _data = self.xy_stage.microstep * self.xy_stage.y_axis.get_position()

                self._send_reply(reply='move_abs', _type='STANDARD', sender='stage', data=_data)

            elif cmd == 'set_speed':
                axis = cmd_data['axis']
                if axis == 'x':
                    self.xy_stage.set_speed(cmd_data['speed'], self.xy_stage.x_axis, unit=cmd_data['unit'])
                elif axis == 'y':
                    self.xy_stage.set_speed(cmd_data['speed'], self.xy_stage.y_axis, unit=cmd_data['unit'])

                self._send_reply(reply='set_speed', _type='STANDARD', sender='stage')

            elif cmd == 'prepare':
                self.xy_stage.prepare_scan(tcp_address=self._tcp_addr(port=self.tcp_setup['port']['stage']),
                                           adc_name=self.adc_name,
                                           **cmd_data)
                _data = {'n_rows': self.xy_stage.scan_params['n_rows'], 'rows': self.xy_stage.scan_params['rows']}

                self._send_reply(reply='prepare', _type='STANDARD', sender='stage', data=_data)

            elif cmd == 'scan':
                self.xy_stage.scan_device()
                self._send_reply(reply='scan', _type='STANDARD', sender='stage')

            elif cmd == 'stop':
                if not self.xy_stage.stop_scan.is_set():
                    self.xy_stage.stop_scan.set()
                self._send_reply(reply='stop', _type='STANDARD', sender='stage')

            elif cmd == 'finish':
                if not self.xy_stage.finish_scan.is_set():
                    self.xy_stage.finish_scan.set()
                self._send_reply(reply='finish', _type='STANDARD', sender='stage')

            elif cmd == 'pos':
                pos = [x.get_position() * self.xy_stage.microstep for x in (self.xy_stage.x_axis, self.xy_stage.y_axis)]
                pos[1] = self.xy_stage.microstep * self.xy_stage.y_range_steps[-1] - pos[1]
                self._send_reply(reply='pos', _type='STANDARD', sender='stage', data=pos)

            elif cmd == 'get_speed':
                speed = [self.xy_stage.get_speed(a, unit='mm/s') for a in (self.xy_stage.x_axis, self.xy_stage.y_axis)]
                self._send_reply(reply='get_speed', _type='STANDARD', sender='stage', data=speed)

            elif cmd == 'home':
                self.xy_stage.home_stage()
                self._send_reply(reply='home', _type='STANDARD', sender='stage')

            elif cmd == 'no_beam':
                if cmd_data:
                    if not self.xy_stage.no_beam.is_set():
                        self.xy_stage.no_beam.set()
                else:
                    if self.xy_stage.no_beam.is_set():
                        self.xy_stage.no_beam.clear()
                self._send_reply(reply='no_beam', _type='STANDARD', sender='stage', data=cmd_data)

        # Set busy False after executed cmd
        self._busy_cmd = False

    def run(self):

        # Create context; needs to be within run(); sockets have to be created within the respective thread
        self.context = zmq.Context()

        # Main process runs command receive loop
        self.recv_cmd()

        # Logging to user
        logging.info("IrradServer with PID {} is shutting down...".format(self.ident))


if __name__ == '__main__':
    port = sys.argv[1]
    irrad_server = IrradServer(port)
    irrad_server.start()
    irrad_server.join()
