==================================
Irrad_Control
==================================

Introduction
============

``irrad_control`` is a GUI-based control and data visualization software for the irradiation facility at the HISKP cyclotron of Bonn University.

Installation
============

You have to have Python 2/3 with the following packages installed:

- numpy
- scipy
- pyyaml
- pyzmq
- pyqt
- `pyqtgraph <http://pyqtgraph.org/>`_
- paramiko

It's recommended to use a Python environment like `Miniconda <https://conda.io/miniconda.html>`_. After installation you can use Minicondas package manager ``conda`` and ``pip`` to install the required packages

.. code-block:: bash

   conda install numpy scipy pyyaml pyqt pyzmq paramiko

.. code-block:: bash

   pip install git+https://github.com/pyqtgraph/pyqtgraph.git@pyqtgraph-0.10.0

To finally install ``irrad_control`` run the setup file

.. code-block:: bash

   python setup.py develop

Setup control & DAQ
===================

The irradiation setup is controlled by a RaspberryPi 3 server which handles a XY-Stage as well as an extension
`ADDA board <https://www.waveshare.com/wiki/High-Precision_AD/DA_Board>`_ which is used for beam current measurement.
A ``ssh key`` of the host PC must be copied to the server Raspberry Pi. Create and copy a key via

.. code-block::

   ssh-keygen -b 2048 -t rsa
   ssh-copy-id pi@ip

where ``ip`` is the local ip of within the network. The server is then automatically set up on first use with ``irrad_control``.
