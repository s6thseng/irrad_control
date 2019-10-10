#!/usr/bin/env python
import sys
from setuptools import setup, find_packages  # This setup relies on setuptools since distutils is insufficient and badly hacked code

# Figure out if we're installing on control PC or on server
try:
    _server = True if sys.argv[1] == 'server' else False
except IndexError:
    _server = False

version = '1.0.1'
author = 'Pascal Wolf'
author_email = 'wolf@physik.uni-bonn.de'

with open('requirements.txt' if not _server else 'requirements_server.txt') as f:
    required = f.read().splitlines()

# Make dict to pass to setup
setup_kwargs = {'name': 'irrad_control',
                'version': version,
                'description': 'Control software for irradiation facility at HISKP cyclotron at Bonn University',
                'url': 'https://github.com/SiLab-Bonn/irrad_control',
                'license': 'MIT License',
                'long_description': '',
                'author': author,
                'maintainer': author,
                'author_email': author_email,
                'maintainer_email': author_email,
                'packages': find_packages(),
                'setup_requires': ['setuptools'],
                'install_requires': required,
                'include_package_data': True,  # accept all data files and directories matched by MANIFEST.in or found in source control
                'package_data': {'': ['README.*', 'VERSION'], 'docs': ['*'], 'examples': ['*']},
                'keywords': ['radiation damage', 'NIEL', 'silicon', 'irradiation', 'proton', 'fluence'],
                'platforms': 'any',
                'entry_points': {'console_scripts': ['irrad_control = irrad_control.main:main']}
                }

# Remove "server" from sys.argv and entry_points from server setup dict
if _server:
    del sys.argv[1]
    del setup_kwargs['entry_points']

# Setup
setup(**setup_kwargs)

