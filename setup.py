#!/usr/bin/env python
from setuptools import setup, find_packages  # This setup relies on setuptools since distutils is insufficient and badly hacked code

version = '0.0.1'
author = 'Pascal Wolf'
author_email = 'wolf@physik.uni-bonn.de'

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    name='irrad_control',
    version=version,
    description='Control software for irradiation facility at HISKP cyclotron at Bonn University',
    url='https://github.com/SiLab-Bonn/irrad_control',
    license='MIT License',
    long_description='',
    author=author,
    maintainer=author,
    author_email=author_email,
    maintainer_email=author_email,
    packages=find_packages(),
    setup_requires=['setuptools'],
    install_requires=required,
    include_package_data=True,  # accept all data files and directories matched by MANIFEST.in or found in source control
    package_data={'': ['README.*', 'VERSION'], 'docs': ['*'], 'examples': ['*']},
    keywords=['radiation damage', 'NIEL', 'silicon', 'irradiation', 'proton', 'fluence'],
    platforms='any'
)
