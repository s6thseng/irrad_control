import serial
import logging
import time


class ArduinoTempSens(object):
    """Class to read from Arduino temperature sensor setup"""

    # Delimiter which separates the sensor numbers in the command string which is send via serial
    cmd_delimiter = 'T'

    def __init__(self, port="/dev/ttyUSB0", baudrate=9600, timeout=5, ntc_lim=(-55, 125)):
        super(ArduinoTempSens, self).__init__()

        self.ntc_lim = ntc_lim  # Store temperature limits of NTC thermistor

        # Make nice serial interface
        try:
            self.interface = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            time.sleep(2)  # Sleep to allow Arduino to reboot caused by serial connection

        # Catch exception and log instead of raising error because we use this in a multi-threaded environment
        except serial.SerialException:
            logging.error("Could not connect to port {}. Maybe it is used by another process?".format(port))
            self.interface = None

        # Check connection; if we have one, this resets the Arduino and causes reboot. We must wait before we write to serial
        if self.interface is not None:

            # Check connection by writing invalid data and receiving answer
            self.interface.write('{}100'.format(self.cmd_delimiter).encode())
            test_res = float(self.interface.readline().strip())

            if test_res == 999.:
                logging.debug("Serial connection to Arduino temperature sensor established.")
            else:
                logging.error("No reply on serial connection to Arduino temperature sensor.")

    def get_temp(self, sensor):
        """Gets temperature of sensor where 0 <= sensor <= 7 is the physical pin number of the sensor on
        the Arduino analog pin. Can also be a list of ints."""

        if self.interface is None:
            logging.warning("Serial interface to Arduino temperature sensor not established. Retry!")
            return

        # Make int sensors to list
        sensor = sensor if isinstance(sensor, list) else [sensor]

        # Create string to send via serial which will return respective temperatures
        cmd = ''.join(['{}{}'.format(self.cmd_delimiter, s) for s in sensor]).encode()

        # Send via serial interface
        self.interface.write(cmd)

        # Get result; make sure we get the correct amount of results
        res = [999] * len(sensor)
        for i in range(len(sensor)):
            try:
                res[i] = float(self.interface.readline().strip())
            # Timeout of readline returned empty string which cannot be converted to float
            except ValueError:
                logging.error("Timeout for reading of temperature sensor {}.".format(sensor[i]))

        # Make return dict
        temp_data = dict(zip(sensor, res))

        # Check results;
        for j in range(len(res)):
            if res[j] == 999:  # 999 is error code from Arduino firmware
                logging.error("Temperature sensor {} could not be read.".format(sensor[j]))
                del temp_data[sensor[j]]

            # If we're not in the correct temperature region
            elif not self.ntc_lim[0] <= res[j] <= self.ntc_lim[1]:
                temp = 'low' if res[j] < self.ntc_lim[0] else 'high'
                msg = "Temperature sensor {} reads extremely {} temperature. Is the thermistor connected correctly?".format(sensor[j], temp)
                logging.warning(msg)

        return temp_data
