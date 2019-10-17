#-------------------------------------------------------------------------------
# Name:        Ruuvi
# Purpose:     DEcodes specific data from Ruuvi advertisement frame
#
# Author:      Laurent Carré
#
# Created:     18/08/2019
# Copyright:   (c) Laurent Carré Sterwen Technologies 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import math

import BLE_Client


class RuuviRaw:
    '''
    Decodes data from RuuviTag with Data Format 3
    Protocol specification:
    https://github.com/ruuvi/ruuvi-sensor-protocols
    https://github.com/ttu/ruuvitag-sensor/blob/master/ruuvitag_sensor/decoder.py
    '''
    def __init__(self,device):
        self._device=device

    def _get_temperature(self, data):
        '''Return temperature in celsius'''
        temp = (data[2] & ~(1 << 7)) + (data[3] / 100)
        sign = (data[2] >> 7) & 1
        if sign == 0:
            return round(temp, 2)
        return round(-1 * temp, 2)

    def _get_humidity(self, data):
        '''Return humidity %'''
        return data[1] * 0.5

    def _get_pressure(self, data):
        '''Return air pressure hPa'''
        pres = (data[4] << 8) + data[5] + 50000
        return pres / 100

    def _get_acceleration(self, data):
        '''Return acceleration mG'''
        acc_x = self.twos_complement((data[6] << 8) + data[7], 16)
        acc_y = self.twos_complement((data[8] << 8) + data[9], 16)
        acc_z = self.twos_complement((data[10] << 8) + data[11], 16)
        return (acc_x, acc_y, acc_z)

    def _get_battery(self, data):
        '''Return battery mV'''
        return (data[12] << 8) + data[13]

    def decode_data(self):
        '''
        Decode sensor data.
        Returns:
            dict: Sensor values
        '''

        byte_data = bytearray.fromhex(self._device.mfgData())
        acc_x, acc_y, acc_z = self._get_acceleration(byte_data)
        return {
            #'data_format': 3,
            'relative_humidity': self._get_humidity(byte_data),
            'temperature': self._get_temperature(byte_data),
            'pressure': self._get_pressure(byte_data),
            'battery': self._get_battery(byte_data),
            'acceleration': math.sqrt(acc_x * acc_x + acc_y * acc_y + acc_z * acc_z),
            'acceleration_x': acc_x,
            'acceleration_y': acc_y,
            'acceleration_z': acc_z
        }



    def twos_complement(self,value, bits):
        if (value & (1 << (bits - 1))) != 0:
            value = value - (1 << bits)
        return value

    def rshift(self,val, n):
        '''
        Arithmetic right shift, preserves sign bit.
        https://stackoverflow.com/a/5833119 .
        '''
        return (val % 0x100000000) >> n

def main():
    pass

if __name__ == '__main__':
    main()
