#!/usr/bin/python3

#   n56fu.py

#   Module for getting data from the Precision Gold N56FU USB multimeter.
#   (and possible rebadges)

#   Note: Made without information on the data, by analysing serial messages.
#   Use or modify freely.

#   Brian Swatton, May 2024
#   Windows update by Ian Cass, June 2024


import sys, os, time
import logging

__version__ = '1.0 b8'
__date__ = '09/06/24 14:16'


try:
    import serial
    import serial.tools.list_ports
except ImportError as impErr:
    print(f"[Error]: Failed to import - {impErr.args[0]}")
    print('\n !  This program requires the python module "pyserial"')
    print(' !  to be installed in your python environment.\n')
    sys.exit(1)


class N56FU(serial.Serial):
    """Class for connecting to an N56FU USB multimeter on a given port"""
    mode0 = {32:'auto', 16:"dc", 8:'ac', 4:'rel', 2:'hold'}
    mode1 = {32:'max', 16:'min'}
    mult = {128:('u',1e-6), 64:('m',1e-3), 32:('k',1e3), 16:('M',1e6), 2:('%',1), 0:('',1)}
    units = {128:'V', 64:"A", 32:'R', 16:'hFE', 8:'Hz', 4:'F', 2:'tC', 1:'tF' , 0:''}
    function = {128:'Voltage',
                64:"Current",
                32:'Resistance',
                16:'hFE',
                8:'Frequency',
                4:'Capacitance',
                2:'Centigrade',
                1:'Fahrenheit',
                0:'Duty Cyle'}

    @classmethod
    def find_ports(cls) -> list:
        """Discover ports for connected N56FU meters"""
        logging.debug("Looking for ports")
        ports = []
        for port in serial.tools.list_ports.comports():
            device = port.device
            logging.debug(f"Found port {device}")
            if N56FU.try_port(device):
                logging.debug(f"Port {device} is an N56FU")
                ports.append(device)
        return ports

    @classmethod
    def try_port(cls, dev) -> bool:
        """Looks for meter data on a possible port"""
        if sys.platform == 'linux' and dev[:11] != '/dev/ttyUSB':
            return False
        try:
            logging.debug(f"Testing port {dev}")
            tty = serial.Serial(port=dev, baudrate=2400, timeout=2)
            timeout = time.time() + tty.timeout
            while time.time() < timeout and tty.in_waiting < 14:
                pass
            if not tty.in_waiting:
                tty.close()
                return False
            line = tty.read_until(b'\r\n')
            tty.close()
            if len(line) == 14 and line[0] in [43, 45]:
                logging.debug(f"Found an N56FU on port {dev}")
                return True
            return False
        except serial.SerialException as Error:
            logging.error(f"An error ocurred whilst testing port {dev}: {Error}")
            return False

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.baudrate = 2400
        self.timeout = 2
        self.open()


    def get_raw(self, flush=True):
        """Get a raw frame, usually flushing the buffer first to get current data."""
        if flush:
            self.reset_input_buffer()

        data = self.get_frame()
        if data[0] == '!':
            return data

        if len(data) != 14:
            data = self.get_frame()

        if len(data) != 14:
            data = '!length'
        return data


    def get_frame(self):
        """Reads to the next end of frame"""
        data = bytes()
        crlf = False
        while not crlf:
            data += bytes(self.read(1))
            if len(data) == 0:
                data = '!timeout'
                break
            if len(data) > 1:
                crlf = data[-2:] == b'\r\n'
        return data


    def get_reading(self, flush=True):
        """Returns a humanized reading string"""
        state = self.get_state()

        if type(state) is str:
            # It's an error
            return state

        reading = f"{state['display']} {state['mult']}{state['units']}"
        for mode in state['modes']:
            reading += f' {mode}'
        return reading


    def _display(self, raw):
        """Returns the value displayed on the meter from a raw frame, as a string"""
        data = raw[:8].decode()
        digits = data[:5]
        dp = int(data[6])
        dp = 3 if dp == 4 else dp   # for some reason!
        status = raw[7:-2]
        reading = digits if dp == 0 else f'{digits[:dp+1]}.{digits[dp+1:]}'
        return reading


    def get_state(self, flush=True):
        """Returns a dictionary of a decoded frame or '!timeout' string"""
        raw = self.get_raw(flush)
        if raw[0] == '!':
            return raw
        status = raw[7:-2]

        idport = self.port.split('/dev/')[1] if sys.platform == 'linux' else self.port
        self.id = f'n56fu-{idport}'
        state = { 'id':self.id, 'info':''}

        state['display'] = self._display(raw)
        state['function'] = N56FU.function[status[3]]
        state['modes'] = []
        for mode in N56FU.mode0:
            if status[0] & mode == mode:
                state['modes'].append(N56FU.mode0[mode])

        for mode in N56FU.mode1:
            if status[1] & mode == mode:
                state['modes'].append(N56FU.mode1[mode])

        if status[1] == 2:  # pesky nano multiplier in mode1 byte
            state['mult'] = 'n'
            factor = 1e-9
        else:
            state['mult'] = N56FU.mult[status[2]][0]
            factor = N56FU.mult[status[2]][1]

        if state['display'][1] == '?':
            state['value'] = 0
        else:
            state['value'] = float(state['display']) * factor

        state['units'] = N56FU.units[status[3]]
        state['bargraph'] = status[4]

        return state


    def is_set(self, function: str, modes: list, flush: bool =True) -> bool:
        """Confirms or denies a setting of function with modes"""
        lc_modes = [ mode.lower() for mode in modes]
        state = self.get_state(flush)
        if state['function'].lower() != function.lower():
            return False
        for mode in lc_modes:
            if mode not in state['modes']:
                return False
        for mode in state['modes']:
            if mode not in lc_modes:
                return False
        return True

# End of N56FU class


##################################################################
# Main program

if __name__ == '__main__':
    print(f'\n  Module: n56fu v{__version__}, {__date__}  ~ Brian Swatton\n')
    print('  For reading the N56FU USB multimeter.')
    print('  Intended for import.\n')

    #logging.basicConfig(level=logging.DEBUG)

    ports = N56FU.find_ports()

    if ports:
        m = N56FU(ports[0])
        while True:
            print(f'  {m.get_reading()}\r', end='')
    else:
        print('No meter found\n')
