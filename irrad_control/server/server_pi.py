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
from collections import Iterable, defaultdict
from zmq.log import handlers
from external_packages.PiPyADC.ADS1256_definitions import *
from external_packages.PiPyADC.pipyadc import ADS1256


class IrradServer(multiprocessing.Process):

    def __init__(self, config):
        super(IrradServer, self).__init__()
        
        # Process info
        self.process = psutil.Process(self.ident)

        # check config for needed data
        self._check_config(config)

        # config
        self.config = config
        
        # 0MQ related socket types
        self.cmd_type = zmq.REP
        self.data_type = zmq.PUB
        self.log_type = zmq.PUB
        
        self._setup_adc()
        
        self.exit = multiprocessing.Event()
        
        #self._setup_zmq()
        #self._setup_logging()

    def _check_config(self, config):
        """Checks whether all required info is in config"""

        reqs = {'ports': ['log', 'data', 'cmd'], 'logging': ['level'], 'devices': None, 'name': None, 'adc_channels': None}
        missing_reqs = []
        missing_sub_reqs = defaultdict(list)

        # loop over all requirements and respective fields
        for req in reqs:
            if req not in config:
                missing_reqs.append(req)
            else:
                if config[req] and isinstance(reqs[req], Iterable):
                    for sub_req in reqs[req]:
                        if sub_req not in config[req]:
                            missing_sub_reqs[req].append(sub_req)

        msg = None

        if missing_reqs:
            msg = 'Requirement(s) in configuration is(are) missing: {}'.format(', '.join(missing_reqs))

        if missing_sub_reqs:
            msg = '' if msg is None else msg
            tmp_msg = ''
            for req in missing_sub_reqs:
                tmp_msg += '{} of requirement {}'.format(', '.join(missing_sub_reqs[req]), req)
            msg += 'Field(s) of requirement(s) in configuration is(are) missing: {}'.format(tmp_msg)

        if msg:
            raise ValueError(msg)
        
        if len(config['ports']['cmd']) != len(config['devices']):
            raise ValueError('Command ports have to equal to number of devices!')

    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def _setup_zmq(self):
        """Setup of all 0MQ related sockets"""

        # create context; threadsafe, sockets though have to be created within the thread of their context
        self.context = zmq.Context()
        self.cmd_sockets = {}

        # create several sockets for publishing data and incoming commands
        # command sockets; need to set socket option to subscribe to correct commands
        for i, dev in enumerate(self.config['devices']):
            self.cmd_sockets[dev] = self.context.socket(self.cmd_type)
            # listen to commands comming from host PC
            self.cmd_sockets[dev].connect(self._tcp_addr(self.config['ports']['cmd'][i], ip=self.config['ip']['host']))

        # data publisher
        self.data_pub = self.context.socket(self.data_type)
        self.data_pub.set_hwm(10)  # drop data if too slow
        self.data_pub.bind(self._tcp_addr(self.config['ports']['data']))

    def _setup_logging(self):

        numeric_level = getattr(logging, self.config['logging']['level'].upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: {}'.format(self.config['logging']['level']))
        logging.basicConfig(level=numeric_level)

        # create logging publisher first
        log_pub = self.context.socket(self.log_type)
        log_pub.bind(self._tcp_addr(self.config['ports']['log']))
        handler = handlers.PUBHandler(log_pub)
        logging.getLogger().addHandler(handler)
        
    def _setup_adc(self):
        
        self.adc = ADS1256()
        self.adc.drate = DRATE_100
         # self-calibration
        self.adc.cal_self()
    
        # channels TODO: represent not only positive channels
        self._all_channels = [ch_i|NEG_AINCOM for ch_i in (POS_AIN0, POS_AIN1, POS_AIN2, POS_AIN3,
                                                           POS_AIN4, POS_AIN5, POS_AIN6, POS_AIN7)]
        
        self.adc_channels = [self._all_channels[i] for i in range(len(self.config['adc_channels']))]
        
    def send_data(self):
        
        raw_data = self.adc.read_sequence(self.adc_channels)
        data = dict([(self.config['adc_channels'][i], raw_data[i] * self.adc.v_per_digit) for i in range(len(raw_data))])
        
        self.data_pub.send_json({'timestamp': time.time(), 'data': data})
        
    def run(self):
        
        self._setup_zmq()
        self._setup_logging()
        time.sleep(1)
        
        while True:#self.exit.wait(0.01):
            self.send_data()
            time.sleep(0.1)
        
        
   
if __name__ == '__main__':
    print 'ohhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh'
    
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', nargs='?', help='Configuration yaml file', default=None)
    
    args_parsed = parser.parse_args(sys.argv[1:])
    if not args_parsed.config_file:
        parser.error("You have to specify a configuration file")  # pragma: no cover, sysexit
        
    else:
        with open(args_parsed.config_file, 'r') as in_config_file:
            configuration = yaml.safe_load(in_config_file)
        server_pi = IrradServer(configuration)
        server_pi.start()
        
