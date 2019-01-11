#!/bin/bash
# Setup of RaspberryPi server for the irradiation site

# Miniconda dist for RaspberryPi2/3 url
BERRYCONDA2 = https://github.com/jjhelmus/berryconda/releases/download/v2.0.0/Berryconda2-2.0.0-Linux-armv7l.sh

# Get Berryconda2 as miniconda
echo "Getting Berryconda2 from ${BERRYCONDA2}"
wget $BERRYCONDA2 -O miniconda.sh
chmod +x miniconda.sh

# Install miniconda
bash miniconda.sh -b -p $HOME/miniconda

echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> $HOME/.bashrc
source $HOME/miniconda/bin/activate

# Install python packages
conda config --set always_yes yes
conda install pyzmq numpy pyyaml pip

# Upgrade pip
pip install --upgrade pip
pip install wiringpi zaber.serial
