import zmq
import time
import numpy as np


class DataFaker:

    def __init__(self, daq_config):

        self.daq_config = daq_config
        self.url = 'tcp://*:%i' % self.daq_config['tcp']['port']['raw_data']
        self.context = zmq.Context()
        self.data_pub = self.context.socket(zmq.PUB)
        self.data_pub.set_hwm(10)
        self.data_pub.bind(self.url)

    def fake_data(self):
        """Make fake data"""
        data = self.daq_config['daq']
        adcs = data.keys()
        channels = dict([(adc, data[adc]['channels']) for adc in adcs])
        n_channels = dict([(adc, len(channels[adc])) for adc in adcs])
        l, h = 1.0, 5.0
        try:
            while True:
                for adc in adcs:
                    _fd = np.random.uniform(l, h, n_channels[adc])
                    _meta = {'timestamp': time.time(), 'name': adc, 'type': 'raw'}
                    _data = dict([(channels[adc][i], _fd[i]) for i in range(n_channels[adc])])
                    fd = {'meta': _meta, 'data': _data}
                    self.data_pub.send_json(fd)
                    time.sleep(0.05)  # fake at 20 Hz
        except KeyboardInterrupt:
            pass
