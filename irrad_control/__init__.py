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

    # Load network and data acquisition config
    with open(os.path.join(config_path, 'network_config.yaml'), 'r') as nc:
        network_config = yaml.safe_load(nc)
    del nc

    with open(os.path.join(config_path, 'daq_config.yaml'), 'r') as dc:
        daq_config = yaml.safe_load(dc)
    del dc

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
