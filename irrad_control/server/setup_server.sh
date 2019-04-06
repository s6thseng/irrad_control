#!/bin/bash
# Setup of RaspberryPi server for the irradiation site

MINICONDA_PATH=$HOME/miniconda

# Check whether miniconda is installed in the foreseen directory MINICONDA_PATH
if [ ! -d "$MINICONDA_PATH" ]; then
	
	echo 'Server missing Miniconda Python. Setting up...'
	
	# Miniconda dist for RaspberryPi2/3 url
	BERRYCONDA2='https://github.com/jjhelmus/berryconda/releases/download/v2.0.0/Berryconda2-2.0.0-Linux-armv7l.sh'
	
	# Get Berryconda2 as miniconda
	echo "Getting Berryconda2 from ${BERRYCONDA2}"
	wget --tries 0 --waitretry 5 $BERRYCONDA2 -O miniconda.sh
	chmod +x miniconda.sh
	
	# Install miniconda
	bash miniconda.sh -b -p $HOME/miniconda
	rm miniconda.sh
	
	echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> $HOME/.bashrc
	source $HOME/miniconda/bin/activate
	
	# Install python packages
	conda config --set always_yes yes
	conda install pyzmq numpy pyyaml pip
	
	# Upgrade pip and install needed packages from pip
	pip install --upgrade pip
	pip install wiringpi zaber.serial
	
	echo 'Server setup successful'
else
	echo 'Server is set up'
fi
