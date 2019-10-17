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

import binascii
import struct

import btle
from btle import UUID, BTLEException


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

class Eddystone:

    serviceUUID=0xFEAA
    serviceUUID_H="AAFE"
    UID_Frame=0x00
    URL_Frame=0x10
    TLM_Frame=0x20
    EID_Frame=0x30
    Reserved=0x40
    UID_Frame_H="00"
    URL_Frame_H="10"
    TLM_Frame_H="20"
    EID_Frame_H="30"
    Reserved_H="40"
    URL_Prefix=['http://www.','https://www.','http://','https://']
    URL_Suffix=['.com/','.org/','.edu/','.net/','.info/','.biz/','.gov/','.com','.org','.edu','.net','.info','.biz','.gov']
    @staticmethod
    def decodeURL(data):
        s=Eddystone.URL_Prefix[data[0]]
        i=1
        for c in data[1:] :
            if c > 0x20 and c < 0x7F :
                s += chr(c)
            else :
                break
            i += 1
        s += Eddystone.URL_Suffix[data[i]]
        for c in data[i+1:]:
            s += chr(c)
        return s



class iBeacon:

    Apple_MfgID=0x004C

    @staticmethod
    def check(data):
        if data[:4] == '0215' :
            return True
        else:
            return False

    @staticmethod
    def strUUID(binVal) :
        s = binascii.b2a_hex(binVal).decode('utf-8')
        return "-".join([s[0:8], s[8:12], s[12:16], s[16:20], s[20:32]])




class BLE_DataService():

    BTRAW=0
    INT=1
    FLOAT=2
    STRING=3
    UUID=4
    BYTES=5

    types=("BTRAW","INT","FLOAT","STRING","UUID","BYTES")

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
    @staticmethod
    def service(id):
        try:
            service=BLE_DataService.services[id]
            return service
        except KeyError :
            return BLE_DataService.services[0]

    @staticmethod
    def type_string(type):
        return BLE_DataService.types[type]

    def __init__(self,id,name,convert,type):
        self._id=id
        self._name=name
        self._convert=convert
        self._type=type

    def type(self):
        return self._type

    def name(self):
        return self._name

    @staticmethod
    def getIdFromName(name):
        return BLE_DataService.name_index[name]

def convertH4Bfloat(value) :
    lb=int(value[0:2],16)
    hb=int(value[2:4],16)*256
    return float(hb+lb)/100.
def convertH4Bint(value):
    lb=int(value[0:2],16)
    hb=int(value[2:4],16)*256
    return hb+lb
def convertH2Bint(value) :
    return int(value[0:2],16)
def convertH4BDJson(value):
    lb=int(value[0:2],16)
    flag= lb & 1
    lb = lb >> 1
    hb = int(value[2:4],16)*128
    val = hb + lb
    s="{\"level\":%d,\"counter\":%d}" % (flag,val)
    return s
def convertH3ValJson(value):
    x=convertH4Bint(value)
    y=convertH4Bint(value[4:])
    z= convertH4Bint(value[8:])
    s="{\"x\":%d,\"y\":%d,\"z\":%d}" % (x,y,z)
    return s
def donotConvert(value):
    return value

data_services= [
    BLE_DataService(0x0000,"Default Service",donotConvert,BLE_DataService.BTRAW),
    BLE_DataService(0x2A19,"battery-level",convertH2Bint,BLE_DataService.INT) ,
    BLE_DataService(0x2A6E,"temperature",convertH4Bfloat,BLE_DataService.FLOAT),
    BLE_DataService(0x2A6F,"humidity",convertH2Bint,BLE_DataService.INT),
    BLE_DataService(0x2A06,"alert-level",convertH4BDJson,BLE_DataService.STRING),
    BLE_DataService(0x2A3F,"alert-status",convertH2Bint,BLE_DataService.INT),
    BLE_DataService(0x2AA1,"magnetic-flux-density-3D",convertH3ValJson,BLE_DataService.STRING),
    BLE_DataService(0x2A58,"analog", convertH4Bint, BLE_DataService.INT),
    BLE_DataService(Eddystone.serviceUUID,"eddystone",donotConvert,BLE_DataService.BTRAW),
    BLE_DataService(0x180F,"battery-level",convertH2Bint,BLE_DataService.INT) # BUG ELA
]

class BLE_ServiceData():

    def __init__(self,serviceid,data):
        self._uuid=serviceid
        self._service=BLE_DataService.service(serviceid)
        self._value=BLE_DataService.decode(serviceid,data)

    def service_uuid(self):
        return self._uuid
    def type(self):
        return self._service.type()
    def value(self):
        return self._value
    def name(self):
        if self._service._id != 0 :
            return self._service.name()
        else:
            return "%04X" % self._uuid


def registerDataServices():
    for s in data_services :
        BLE_DataService.register(s)

##########################################################################
#
def toInt(b):
    # transform the bytes in int
    l=len(b)
    if l == 1 :
        it=struct.unpack('B',b)
    elif l == 2 :
        it=struct.unpack('H',b)
    elif l == 4:
        it= struct.unpack('L',b)
    else:
        raise ValueError
    return it[0]

def toFloat(b):
    l=len(b)
    if l == 4:
        ft=struct.unpack('f',b)
    else:
        raise ValueError
    return ft[0]

def BLE_convert(val_raw,typeVar):
    if typeVar == 3:
        val=val_raw.decode('utf-8')
    elif typeVar == 1:
        val=toInt(val_raw)
    elif typeVar == 2:
        val=toFloat(val_raw)
    elif typeVar == 4:
        val=val_rawdecode('utf-8')
    elif typeVar == 5:
        val=binascii.b2a_hex(val_raw).decode('utf-8')
    else:
        val=binascii.b2a_hex(val_raw).decode('utf-8')
    return val

def main():
    pass

if __name__ == '__main__':
    main()
