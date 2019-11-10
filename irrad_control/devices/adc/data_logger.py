#!usr/bin/python

import sys
import time
import argparse
from irrad_control.devices.adc.ADS1256_definitions import *
from irrad_control.devices.adc.pipyadc import ADS1256


def logger(channels, outfile, rate=1, n_digits=3, mode='s', show_data=False):
    """
    Method to log the data read back from a ADS1256 ADC to a file.
    Default is to read from positive AD0-AD7 pins from 0 to 7 for single-
    ended measurement. For differential measurement pin i and i + 1 are
    selected as inputs. Only as many channels are read as there are names
    in the channel list.

    Parameters
    ----------

    channels: list
        list of strings with names of channels
    outfile: str
        string of output file location
    rate: int
        Logging rate in Hz
    n_digits: int
        number of decimal places to be logged into the outfile
    mode: 's' or 'd' or str of combination of both
        string character(s) describing the measurement mode: single-endend (s) or differential (d)
    show_data: bool
        whether or not to show the data every second on the stdout

    Returns
    -------

    """

    # get instance of ADC Board
    adc = ADS1256()

    # self-calibration
    adc.cal_self()

    # channels TODO: represent not only positive channels
    _all_channels = [POS_AIN0, POS_AIN1,
                     POS_AIN2, POS_AIN3,
                     POS_AIN4, POS_AIN5,
                     POS_AIN6, POS_AIN7]
    # gnd
    _gnd = NEG_AINCOM

    # get actual channels by name
    if len(channels) > 8 and mode == 's':
        raise ValueError('Only 8 single-ended input channels exist')
    elif len(channels) > 4 and mode == 'd':
        raise ValueError('Only 4 differential input channels exist')
    else:
        # only single-ended measurements
        if mode == 's':
            actual_channels = [_all_channels[i] | _gnd for i in range(len(channels))]

        # only differential measurements
        elif mode == 'd':
            actual_channels = [_all_channels[i] | _all_channels[i + 1] for i in range(len(channels))]

        # mix of differential and single-ended measurements
        elif len(mode) > 1:
            # get configuration of measurements
            channel_config = [1 if mode[i] == 's' else 2 for i in range(len(mode))]

            # modes are known and less than 8 channels in total
            if all(m in ['d', 's'] for m in mode) and sum(channel_config) <= 8:
                i = j = 0
                actual_channels = []

                while i != sum(channel_config):
                    if channel_config[j] == 1:
                        actual_channels.append(_all_channels[i] | _gnd)
                    else:
                        actual_channels.append(_all_channels[i] | _all_channels[i + 1])
                    i += channel_config[j]
                    j += 1

                if len(actual_channels) != len(channels):
                    raise ValueError('Number of channels (%i) not matching measurement mode ("%s" == %i differential & %i single-ended channels)!'
                                     % (len(channels), mode, mode.count('d'), mode.count('s')))
                else:
                    raise ValueError(
                        'Unsupported number of channels! %i differential (%i channels) and %i single-ended (%i channels) measurements but only 8 channels total'
                        % (mode.count('d'), mode.count('d') * 2, mode.count('s'), mode.count('s')))
        else:
            raise ValueError('Unknown measurement mode %s. Supported modes are "d" for differential and "s" for single-ended measurements.' % mode)

    # open outfile
    with open(outfile, 'w') as out:

        # write info header
        out.write('# Date: %s \n' % time.asctime())
        out.write('# Measurement in %s mode.\n' % ('differential' if mode == 'd' else 'single-ended' if mode == 's' else mode))
        out.write('# Timestamp / s\t' + ' \t'.join('%s / V' % c for c in channels) + '\n')

        # try -except clause for ending logger
        try:
            print 'Start logging channel(s) %s to file %s.\nPress CTRL + C to stop.\n' % (', '.join(channels), outfile)
            start = time.time()
            while True:

                readout_start = time.time()

                # get current channels
                raw = adc.read_sequence(actual_channels)
                volts = [b * adc.v_per_digit for b in raw]

                readout_end = time.time()

                # write timestamp to file
                out.write('%f\t' % time.time())

                # write voltages to file
                out.write('\t'.join('%.{}f'.format(n_digits) % v for v in volts) + '\n')

                # wait
                time.sleep(1. / rate)

                # User feedback about logging and readout rates every second
                if time.time() - start > 1:

                    # actual logging and readout rate
                    logging_rate = 1. / (time.time() - readout_start)
                    readout_rate = 1. / (readout_end - readout_start)

                    # print out with flushing
                    log_string = 'Logging rate: %.2f Hz' % logging_rate + ',\t' + 'Readout rate: %.2f Hz for %i channel(s)'\
                                 % (readout_rate, len(actual_channels))

                    # show values
                    if show_data:
                        # print out with flushing
                        log_string += ': %s' % ', '.join('{}: %.{}f V'.format(channels[i], n_digits) % volts[i] for i in range(len(volts)))

                    # print out with flushing
                    sys.stdout.write('\r' + log_string)
                    sys.stdout.flush()

                    # overwrite
                    start = time.time()

        except KeyboardInterrupt:
            print '\nStopping logger...\nClosing %s...' % str(outfile)

    print 'Finished'


if __name__ == '__main__':
    # parse args from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--channels', help='Channel names', required=True)
    parser.add_argument('-o', '--outfile', help='Output file', required=True)
    parser.add_argument('-r', '--rate', help='Timeout between loggings', required=False)
    parser.add_argument('-d', '--digits', help='Digits for logged data', required=False)
    parser.add_argument('-m', '--mode', help='d for differential or s for single-ended mode', required=False)
    parser.add_argument('-s', '--show', help='Show data values', required=False)
    args = vars(parser.parse_args())

    # read arsed args and convert if necessary
    channels = args['channels'].split(' ')
    outfile = args['outfile']
    rate = 1 if args['rate'] is None else float(args['rate'])
    n_digits = 3 if args['digits'] is None else int(args['digits'])
    mode = 's' if args['mode'] is None else args['mode']
    show_data = False if args['show'] is None else bool(int(args['show']))

    # start logger
    logger(channels=channels, outfile=outfile, rate=rate, n_digits=n_digits, mode=mode, show_data=show_data)
