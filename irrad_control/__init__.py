# Different errrors are raised in Python2/3
try:
    ModuleNotFoundError  # Python >= 3.6
except NameError:
    ModuleNotFoundError = ImportError  # Python < 3.6

try:
    import yaml
    _YAML = True  # irrad_control on DAQ / Host PC
except ModuleNotFoundError:
    _YAML = False  # irrad_control on server

if _YAML:

    # Imports
    import os
    from collections import OrderedDict

    # Paths
    package_path = os.path.dirname(__file__)
    config_path = os.path.join(package_path, 'config')

    # Shell script to config server
    config_server_script = os.path.join(package_path, 'configure_server.sh')

    # Init several dicts with hardware specifications

    # ADS1256 data rates and number of averages ber data rate
    ads1256 = OrderedDict()

    # Data rate in samples per second
    ads1256['drate'] = OrderedDict([(0b11110000, 30000), (0b11100000, 15000), (0b11010000, 7500), (0b11000000, 3750),
                                    (0b10110000, 2000), (0b10100001, 1000), (0b10010010, 500), (0b10000010, 100),
                                    (0b01110010, 60), (0b01100011, 50), (0b01010011, 30), (0b01000011, 25),
                                    (0b00110011, 15), (0b00100011, 10), (0b00010011, 5), (0b00000011, 2.5)])

    # Number of averages for respective data rate
    ads1256['avgs'] = OrderedDict([(30000, 1), (15000, 2), (7500, 4), (3750, 8), (2000, 15), (1000, 30),
                                   (500, 60), (100, 300), (60, 500), (50, 600), (30, 1000), (25, 1200),
                                   (15, 2000), (10, 3000), (5, 6000), (2.5, 12000)])

    # Current resolutions of 5V full-scale output of custom readout electronics in nA
    ro_scales = OrderedDict([('1 %sA' % u'\u03bc', 1000.0), ('0.33 %sA' % u'\u03bc', 330.0),
                             ('0.1 %sA' % u'\u03bc', 100.0), ('33 nA', 33.0), ('10 nA', 10.0), ('3.3 nA', 3.3)])

    # Types of hwd channels needed for interpretation
    with open(os.path.join(config_path, 'roe_output.yaml'), 'r') as ro:
        roe_output = yaml.safe_load(ro)
    del ro

    # Types of hwd channels needed for interpretation
    with open(os.path.join(config_path, 'server_ips.yaml'), 'r') as si:
        server_ips = yaml.safe_load(si)
    del si

    # Proportionality constants between SEM signal and proton beam current
    with open(os.path.join(config_path, 'proportionality_constants.yaml'), 'r') as pc:
        proportionality_constants = yaml.safe_load(pc)
    del pc

    # Proton hardness factors
    with open(os.path.join(config_path, 'hardness_factors.yaml'), 'r') as hf:
        hardness_factors = yaml.safe_load(hf)
    del hf

    # DAQ devices list, eg. SEM
    with open(os.path.join(config_path, 'daq_devices.yaml'), 'r') as dd:
        daq_devices = yaml.safe_load(dd)
    del dd

    # Keep track of xy stage travel
    if not os.path.isfile(os.path.join(package_path, 'devices/stage/xy_stage_stats.yaml')):
        # Open xy stats template and safe a copy
        with open(os.path.join(config_path, 'xy_stage_stats.yaml'), 'r') as xys_l:
            xy_stage_stats_tmp = yaml.safe_load(xys_l)

        with open(os.path.join(package_path, 'devices/stage/xy_stage_stats.yaml'), 'w') as xys_s:
            yaml.safe_dump(xy_stage_stats_tmp, xys_s)

        del xy_stage_stats_tmp, xys_l, xys_s

    with open(os.path.join(package_path, 'devices/stage/xy_stage_stats.yaml'), 'r') as xys:
        xy_stage_stats = yaml.safe_load(xys)
    del xys


