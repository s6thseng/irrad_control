import serial
import logging


class ArduinoTempSens(object):
    """Class to read from Arduino temperature sensor setup"""

    def __init__(self, port="/dev/ttyUSB0", baudrate=9600, timeout=5):
        super(ArduinoTempSens, self).__init__()

        # Make nice serial interface
        try:
            self.interface = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        except serial.SerialException:
            logging.error("Could not connect to port {}. Maybe it is used by another process?".format(port))

    def get_temp(self, sensor):
        """Gets temperature of sensor where 0 <= sensor <= 7 is the physical pin number of the sensor on
        the Arduino analog pin. Can also be a list of ints."""

        # Make int sensors to list
        sensor = sensor if isinstance(sensor, list) else [sensor]

        # Create string to send via serial which will return respective temperatures
        cmd = ''.join(['T{}'.format(s) for s in sensor]).encode()

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
            elif res[j] < -90: # When no NTC thermistor is connected to the circuit, low values are returned
                logging.warning("Temperature sensor {} reads extremely low temperature. Is the thermistor connected correctly?".format(sensor[j]))

        return temp_data






