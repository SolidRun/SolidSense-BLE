# -*- coding: UTF-8 -*-
#-------------------------------------------------------------------------------
# Name:        BLE_Data
# Purpose:     Set of classes for BLE data processing
#
# Author:      Laurent
#
# Created:     14/07/2019
# Copyright:   (c) Laurent Carré - Sterwen Technology 2019
# Licence:     Eclipse 1.0
#-------------------------------------------------------------------------------

import bluepy
from bluepy.btle import UUID, BTLEException


class NordicSerial:
    """
    This class supports definition for the Nordic Serial service over GATT
    """

    nordicService="6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    nordicWrite="6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    nordicNotify="6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    service_uuid=UUID(nordicService)
    write_uuid=UUID(nordicWrite)
    notify_uuid=UUID(nordicNotify)

class BLE_DataService():

    services= {}
    name_index= {}
    @staticmethod
    def register(service):
        BLE_DataService.services[service._id] =service
        BLE_DataService.name_index[service._name] = service._id

    @staticmethod
    def decode(id,data):
        try:
            service=BLE_DataService.services[id]
        except KeyError :
            return data
        return service._convert(data)

    def __init__(self,id,name,convert):
        self._id=id
        self._name=name
        self._convert=convert

    @staticmethod
    def getIdFromName(name):
        return BLE_DataService.name_index[name]

def convertH4Bfloat(value) :
    lb=int(value[0:2],16)
    hb=int(value[2:4],16)*256
    return float(hb+lb)/100.
def convertH2Bint(value) :
    return int(value[0:2],16)

data_services= [
    BLE_DataService(0x2A19,"Battery Level",convertH2Bint) ,
    BLE_DataService(0x2A6E,"Temperature",convertH4Bfloat)
]

def registerDataServices():
    for s in data_services :
        BLE_DataService.register(s)

def main():
    pass

if __name__ == '__main__':
    main()
