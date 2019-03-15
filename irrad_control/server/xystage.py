import time
import logging
import threading
import zmq
from zaber.serial import *


class ZaberXYStage:

    def __init__(self, serial_port="/dev/ttyUSB0"):
        """
        Define the attributes of this Zaber stage. For information please refer to the following links:
        https://www.zaber.com/products/xy-xyz-gantry-systems/XY/details/X-XY-LRQ300BL-E01/features
        https://www.zaber.com/products/linear-stages/X-LRQ-E/details/X-LRQ300BL-E01
        """

        self.model = 'X-XY-LRQ300BL-E01-KX14C-SQ3'

        # Important parameters of each stage
        self.microstep = 0.49609375e-6  # meter
        self.linear_motion_per_rev = 6.35e-3  # meter
        self.steps_per_rev = 200  # steps

        # Initialize the zaber device
        port = AsciiSerial(serial_port)

        # Devices
        self.x_device = AsciiDevice(port, 1)
        self.y_device = AsciiDevice(port, 2)

        # Axis
        self.x_axis = self.x_device.axis(1)
        self.y_axis = self.y_device.axis(1)

        # Travel ranges in microsteps
        self.x_range_steps = [int(self.x_axis.send("get limit.min").data), int(self.x_axis.send("get limit.max").data)]
        self.y_range_steps = [int(self.y_axis.send("get limit.min").data), int(self.y_axis.send("get limit.max").data)]

        # Travel ranges in mm
        self.x_range_mm = [r * self.microstep * 1e3 for r in self.x_range_steps]
        self.y_range_mm = [r * self.microstep * 1e3 for r in self.y_range_steps]

        # y-axis is inverted
        self.home_position = (0, self.y_range_steps[-1])

        # ZMQ related stuff
        self.context = zmq.Context()

        # Emergency stop signal
        self.emergency_stop = threading.Event()

    def update_setup(self, irrad_setup):

        # Update setup
        self.irrad_setup = irrad_setup

        # Extract info and sub setups
        self.adc_name = irrad_setup['daq'].keys()[0]
        self.daq_setup = irrad_setup['daq'][self.adc_name]
        self.tcp_setup = irrad_setup['tcp']

    def _tcp_addr(self, port, ip='*'):
        """Creates string of complete tcp address which sockets can bind to"""
        return 'tcp://{}:{}'.format(ip, port)

    def _check_reply(self, reply):
        """Method to check the reply of a command which has been issued to one of the axes"""

        # Get reply data and corresponding axis
        msg = "{}-axis: {}".format('x' if reply.device_address == 1 else 'y', reply.data)

        # Flags are either 'OK' or 'RJ'
        if reply.reply_flag != 'OK':
            logging.error("Command rejected by {}".format(msg))
            return False

        # Use logging to debug
        logging.debug("Command succeeded: {}".format(msg))
        return True

    def home_x_axis(self):
        """Move x axis to the home position and check and return reply"""
        _reply = self.x_axis.move_abs(self.home_position[0])
        self._check_reply(_reply)
        return _reply

    def home_y_axis(self):
        """Move x axis to the home position and check and return reply"""
        _reply = self.y_axis.move_abs(self.home_position[-1])
        self._check_reply(_reply)
        return _reply

    def speed_to_step_s(self, speed, unit="mm/s"):
        """Convert the speed in some unit to microsteps per second"""

        # Check if unit is okay
        if unit not in ("mm/s", "cm/s", "m/s"):
            logging.warning("Unit of scan speed must be either 'mm/s', 'cm/s' or 'm/s'. Using mm/s!")
            unit = "mm/s"

        # Calculate respective unit conversion factor
        _factor = 1 if unit == "mm/s" else 10 if unit == "cm/s" else 1000

        # Return result as integer; for conversion formula see: https://zaber.com/documents/ZaberSpeedSetting.xls
        return int(_factor * speed * 1.6384 * 1e-3 * 1.0 / self.microstep)

    def speed_to_mm_s(self, speed):
        "Convert integer speed in steps per second to mm per second"
        return float(speed / 1.6384 * 1e3 * self.microstep)

    def speed_to_cm_s(self, speed):
        "Convert integer speed in steps per second to cm per second"
        return self.speed_to_mm_s(speed) * 0.1

    def speed_to_m_s(self, speed):
        "Convert integer speed in steps per second to m per second"
        return self.speed_to_mm_s(speed) * 0.001

    def set_scan_speed_mm_s(self, speed):
        "Set scan speed in mm per second"
        return self.set_speed(self.speed_to_step_s(speed, unit="mm/s"), self.x_axis)

    def set_speed(self, speed, axis):
        """Set the speed at which axis moves for move rel and move abs commands"""

        # Check if axis is known
        if axis not in (self.x_axis, self.y_axis):
            logging.warning("Unknown axis. Abort.")
            return

        # Get maxspeed of current axis
        _axis_maxspeed = int(axis.send("get resolution").data) * 16384

        # Check whether speed is not larger than maxspeed
        if speed > _axis_maxspeed:
            msg = "Maximum speed of this axis is {} mm/s. Speed not updated!".format(self.speed_to_mm_s(_axis_maxspeed))
            logging.warning(msg)
            return

        # Issue command and wait for reply and check
        _reply = axis.send("set maxspeed {}".format(speed))
        self._check_reply(_reply)

        return _reply

    def get_speed(self, axis):
        """Get the speed at which axis moves for move rel and move abs commands"""

        # Check if axis is known
        if axis not in (self.x_axis, self.y_axis):
            logging.warning("Unknown axis. Abort.")
            return

        # Issue command and wait for reply and check
        _reply = axis.send("get maxspeed")
        success = self._check_reply(_reply)

        return 0 if not success else int(_reply.data)

    def get_scan_speed(self, unit="mm/s"):
        "Get speed in mm/cm/m per second"

        if unit not in ("mm/s", "cm/s", "m/s"):
            logging.warning("Unit of scan speed must be either 'mm/s', 'cm/s' or 'm/s'. Using mm/s!")
            unit = "mm/s"

        speed = self.get_speed(self.x_axis)

        return self.speed_to_mm_s(speed) if unit == 'mm/s' else self.speed_to_cm_s(speed) if unit == 'cm/s' else self.speed_to_m_s(speed)

    def accel_to_step_s2(self, accel, unit="mm/s^2"):

        if unit not in ("mm/s^2", "cm/s^2", "m/s^2"):
            logging.warning("Unit of acceleration must be either 'mm/s^2', 'cm/s^2' or 'm/s^2'. Using mm/s^2!")
            unit = "mm/s^2"

        _factor = 1 if unit == "mm/s^2" else 10 if unit == "cm/s^2" else 1000

        return int(_factor * accel * 1.6384 * 1e-7 * 1.0 / self.microstep)

    def accel_to_mm_s2(self, accel):
        return float(accel / 1.6384 * 1e7 * self.microstep)

    def accel_to_cm_s2(self, accel):
        return self.accel_to_mm_s2(accel) * 0.1

    def accel_to_m_s2(self, accel):
        return self.accel_to_mm_s2(accel) * 0.001

    def set_scan_accel_mm_s2(self, accel):
        return self.set_accel(self.accel_to_step_s2(accel, unit="mm/s^2"), self.x_axis)

    def set_accel(self, accel, axis):
        """Set the acceleration at which the axis increases speed for move rel and move abs commands"""

        # Check if axis is known
        if axis not in (self.x_axis, self.y_axis):
            logging.warning("Unknown axis. Abort.")
            return

        _max_accel = 32767

        # Check whether speed is not larger than maxspeed
        if accel > _max_accel:
            msg = "Maximum acceleration of this axis is {} m/s. Accel not updated!".format(0)
            logging.warning(msg)
            return

        # Issue command and wait for reply and check
        _reply = axis.send("set accel {}".format(accel))
        self._check_reply(_reply)

        return _reply

    def get_accel(self, axis):
        """Get the acceleration at which the axis increases speed for move rel and move abs commands"""

        # Check if axis is known
        if axis not in (self.x_axis, self.y_axis):
            logging.warning("Unknown axis. Abort.")
            return

        # Issue command and wait for reply and check
        _reply = axis.send("get accel")
        success = self._check_reply(_reply)

        return 0 if not success else int(_reply.data)

    def calc_accel(self, speed, distance):
        return speed**2.0 / (2.0 * distance)

    def distance_to_steps(self, distance, unit="mm"):

        if unit not in ("mm", "cm", "m"):
            logging.warning("Unit of distance must be either 'mm', 'cm' or 'm'. Using mm!")
            unit = "mm"

        _factor = 1e-3 if unit == "mm" else 1e-2 if unit == "cm" else 1

        return int(_factor * distance / self.microstep)

    def _move_axis_rel(self, distance, axis, unit="mm"):
        """Method to move along the x/y axis relative to the current position"""

        # Get distance in steps
        dist_steps = self.distance_to_steps(distance, unit)

        # get current position
        curr_pos = axis.get_position()

        min_step, max_step = int(axis.send("get limit.min").data), int(axis.send("get limit.max").data)

        # Vertical axis is inverted; multiply with distance with -1
        if axis is self.y_axis:
            dist_steps *= -1

        # Check whether there's still room to move
        if not min_step <= curr_pos + dist_steps <= max_step:
            logging.error("Movement out of travel range. Abort!")
            return

        _reply = axis.move_rel(dist_steps)
        self._check_reply(_reply)

    def move_vertical(self, distance, unit="mm"):
        """Method to move up the y axis relative to the current position"""

        self._move_axis_rel(distance, self.y_axis, unit)

    def move_horizontal(self, distance, unit="mm"):
        """Method to move up the y axis relative to the current position"""

        self._move_axis_rel(distance, self.x_axis, unit)

    def prepare_scan(self, rel_start_point, rel_end_point, n_scans, scan_speed, step_size):
        """Does a complete scan from the current position of the stage"""

        # Current position in steps is relative reference for coordinate system of scan
        self.origin = (self.x_axis.get_position(), self.y_axis.get_position())

        # Scan start position
        self.start_scan = (self.origin[0] - self.distance_to_steps(rel_start_point[0]),
                           self.origin[1] - self.distance_to_steps(rel_start_point[1]))  # inverted y-axis

        # Scan start position
        self.end_scan = (self.origin[0] - self.distance_to_steps(rel_end_point[0]),
                         self.origin[1] - self.distance_to_steps(rel_end_point[1]))  # inverted y-axis

        # Store step size
        self.step_size = step_size
        self.scan_speed = scan_speed
        self.n_scans = n_scans
        self.step_size_steps = self.distance_to_steps(step_size, unit="mm")

        # Calculate number of rows for the scan
        self.n_rows = int(abs(self.end_scan[1] - self.start_scan[1]) / self.step_size_steps)

        self.rows = dict([(row, self.start_scan[1] - row * self.step_size_steps) for row in range(self.n_rows)])

        # Set the scan speed
        self.set_scan_speed_mm_s(scan_speed)

    def do_scan(self):

        self.scan_thread = threading.Thread(target=self._do_complete_scan)
        self.scan_thread.start()

    def _do_complete_scan(self):

        # initialize zmq data publisher
        stage_pub = self.context.socket(zmq.PUB)
        stage_pub.set_hwm(10)
        stage_pub.bind(self._tcp_addr(self.tcp_setup['port']['stage']))

        # Move to start point
        self.x_axis.move_abs(self.start_scan[0])
        self.y_axis.move_abs(self.start_scan[1])

        x_start, x_end = self.start_scan[0], self.end_scan[0]

        _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'stage'}
        _data = {'status': 'init', 'y_step': self.step_size, 'n_rows': self.n_rows, }

        stage_pub.send_json({'meta': _meta, 'data': _data})

        # Loop over all scans; each scan is counted as one coverage of the entire area
        for scan in range(self.n_scans):

            # Determine whether we're going from top to bottom or opposite
            _tmp_rows = range(self.n_rows) if scan % 2 == 0 else reversed(range(self.n_rows))
            _tmp_rows = list(_tmp_rows)

            # Loop over rows
            for row in _tmp_rows:

                if self.emergency_stop.wait(1e-1):
                    break

                self.y_axis.move_abs(self.rows[row])

                # Send start data
                _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'stage'}
                _data = {'status': 'start', 'scan': scan, 'row': row, 'speed': self.get_scan_speed(),
                         'x_start': self.x_axis.get_position() * self.microstep,
                         'y_start': self.y_axis.get_position() * self.microstep}

                stage_pub.send_json({'meta': _meta, 'data': _data})

                self.x_axis.move_abs(x_end if self.x_axis.get_position() == x_start else x_start)

                # Send stop data
                _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'stage'}
                _data = {'status': 'stop',
                         'x_stop': self.x_axis.get_position() * self.microstep,
                         'y_stop': self.y_axis.get_position() * self.microstep}

                stage_pub.send_json({'meta': _meta, 'data': _data})

        # Send finished data
        _meta = {'timestamp': time.time(), 'name': self.adc_name, 'type': 'stage'}
        _data = {'status': 'finished'}

        stage_pub.send_json({'meta': _meta, 'data': _data})

        # Move to the scan start position
        self.x_axis.move_abs(self.start_scan[0])
        self.y_axis.move_abs(self.start_scan[1])

        stage_pub.close()







