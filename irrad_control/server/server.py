import os
import zmq
import sys
import time
import yaml
import multiprocessing
import threading
import logging
import argparse
import psutil
from collections import Iterable, defaultdict, OrderedDict
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

    def __init__(self, cmd_port):
        super(IrradServer, self).__init__()
        
        # Process info
        self.process = psutil.Process(self.ident)
        
        self._send_data = True
        self._recv_cmds = True
        
        self.cmd_port = cmd_port
        
        # List of known commands
        self._cmds = ['setup_zmq']
        
        self.irrad_config = None
        
    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)
        
    def _setup_server(self, irrad_config):
        
        self.irrad_config = irrad_config
        self.adc_name = irrad_config['daq'].keys()[0]
        self.daq_config = irrad_config['daq'][self.adc_name]
        self.tcp_config = irrad_config['tcp']
        
        # Setup logging
        self._setup_logging()
        
        # Setup adc
        self._setup_adc()
        
        data_thread = threading.Thread(target=self.send_data)
        data_thread.start()

    def _setup_logging(self):

        numeric_level = getattr(logging, self.irrad_config['log']['level'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: {}'.format(self.irrad_config['log']['level']))
        logging.basicConfig(level=numeric_level)

        log_pub = self.context.socket(zmq.PUB)
        log_pub.bind(self._tcp_addr(self.tcp_config['port']['log']))
        
        # Create logging publisher first
        handler = handlers.PUBHandler(log_pub)
        logging.getLogger().addHandler(handler)
        
    def _setup_adc(self):
        
        self.adc = ADS1256()
        self.adc.drate = ads1256_drates[self.daq_config['sampling_rate']]
        
        # self-calibration
        self.adc.cal_self()
    
        # channels TODO: represent not only positive channels
        self._all_channels = [ch_i|NEG_AINCOM for ch_i in (POS_AIN0, POS_AIN1, POS_AIN2, POS_AIN3,
                                                           POS_AIN4, POS_AIN5, POS_AIN6, POS_AIN7)]
        
        self.adc_channels = [self._all_channels[i] for i in range(len(self.daq_config['channels']))]
        
    def recv_cmd(self):
        """Receiving commands from tcp://*:port"""
        
        while self._recv_cmds:
            # Cmd must be dict with command as 'cmd' key and 'args', 'kwargs' keys
            cmd_dict = self.server_rep.recv_json()
            if 'cmd' not in cmd_dict:
                logging.error("Command must be dictionary with actual command in cmd_dict['cmd']!")
                self.server_rep.send_json({'reply': 'Error'})
                continue
            self.handle_cmd(cmd_dict)
            
    def handle_cmd(self, cmd_dict):
        
        cmd = cmd_dict['cmd']
        cmd_data = None if 'data' not in cmd_dict else cmd_dict['data']
        
        if cmd == 'setup_server':
            self._setup_server(cmd_data)
            self.server_rep.send_json({'reply': 'server_pid', 'data': self.ident})
            
        if cmd == 'herro':
            self.server_rep.send_json({'reply': 'Herro'})
        
    def send_data(self):
        
        data_pub = self.context.socket(zmq.PUB)
        data_pub.set_hwm(10)  # drop data if too slow
        data_pub.bind(self._tcp_addr(self.tcp_config['port']['raw_data']))
        
        while self._send_data:

            raw_data = self.adc.read_sequence(self.adc_channels)
            _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'raw'}
            _data = dict([(self.daq_config['channels'][i], raw_data[i] * self.adc.v_per_digit) for i in range(len(raw_data))])
            
            data_pub.send_json({'meta': _meta, 'data': _data})
        
    def run(self):
        # Create context; threadsafe, sockets though have to be created within the thread of their context
        self.context = zmq.Context()

        # Creat server socket
        self.server_rep = self.context.socket(zmq.REP)
        self.server_rep.bind(self._tcp_addr(self.cmd_port))
        
        # Main process runs command receive loop
        self.recv_cmd()


if __name__ == '__main__':
    
    port = sys.argv[1]
    irrad_server = IrradServer(port) #'5400')
    irrad_server.start()
