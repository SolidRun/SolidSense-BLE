# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:       BLE Service library running on top of Bluepy
# Purpose:
#              Shall run on LInux only
#
# Author:      Laurent Carre
#
# Created:     15/04/2019
# Copyright:   (c) Laurent Carre - Sterwen Technology 2019
# Licence:     Eclipse 1.0
#-------------------------------------------------------------------------------

import datetime
import time
import fileinput
import logging
import threading
from concurrent import futures

import bluepy
from bluepy.btle import Scanner, DefaultDelegate, Peripheral, UUID, BTLEException

from BLE_Data import *

blelog=logging.getLogger('BLE_Service')

class BLE_ServiceException(Exception):
    pass

##########################################################################

class Channel:
    """
    The Channel class implements a communication channel (Characteristic)
    with a BLE device GATT server
    """
    def __init__(self,device,service,char):
        self._uuid= char.uuid
        self._char=char
        self._device=device

    def read(self):

        if self._device.connected():
            try:
                return self._char.read()
            except IOError as err:
                blelog.error ("BLE GATT read"+str(err) )
                raise
        else:
            blelog.error ("BLE GATT read device not connected")

    def write(self,data):
        if self._device. connected():
            try:
                if type(data)== str :
                    data=data.encode()
                self._char.write(data)
            except IOError as err:
                blelog("BLE GATT Write"+str(err))
                raise
        else:
            blelog.error ("BLE GATT write device not connected")

    def notify(self):
        print ("Notification received")


    def uuidName(self):
        return self._uuid.getCommonName()

    def uuid(self):
        return self._uuid

#####################################################################

class BLE_Device :
    """
    Proxy for a BLE device with or without GATT server capabilities
    The object is created from a scan entry
    """
    def __init__(self,scan_entry):
        self._p=None
        self._connectable=False
        self._connected=False
        self._addr=scan_entry.addr
        self._addrType=  scan_entry.addrType
        self._name=None
        self._services=None
        self._channels=None
        self._service_data=None

    def connect(self):
        if self._name == None :
            dev_name=""
        else:
            dev_name=self._name
        blelog.info ("BLE GATT connecting: "+str(self._addr)+" type "+str(self._addrType)+" Name:"+dev_name)
        if not self._connectable :
            blelog.info("BLE connect : Device is not connectable")
            return False
        try:
            self._p= Peripheral(self._addr,self._addrType)
        except BTLEException as err:
            blelog.error ("BLE GATT Connect"+str(err))
            return False
        self._connected=True
        return True

    def discover(self,service_uuid=None):

        if not self._connected :
            return False

        self._channels={}

        if type(service_uuid) == type(None):
            self._services=self._p.getServices()
        else :
            try:
                service=self._p.getServiceByUUID(service_uuid)
            except BTLEException as err:
                print(err)
                return False
            self._services=[service]

        for service in self._services:
            cl=service.getCharacteristics()
            for c in cl :
                st= c.uuid
                self._channels[st]=Channel(self,service,c)
        return True

    def connected(self):
        return self._connected

    def disconnect(self):
        if self._connected :
            self._p.disconnect()
            self._connected=False

    def reconnect(self):
        if self._connected :
            return True
        try:
            self._p.connect(self._addr,self._addrType)
        except BTLEException as err:
            blelog.error ("BLE GATT reconnect"+str(err))
            return False
        self._connected=True
        return True

    def allowNotification(self) :
        self._p.withDelegate(BLE_Device_Delegate(self) )
        self._handler=BLE_Notification_Handler(self)

    def _waitForNotifications(self,timeout):
        if not self._connected :
            raise BLE_ServiceException('Device not connected')
        try:
            return self._p.waitForNotifications(timeout)
        except BTLEException as err:
            blelog.error('BLE Wait for notification:'+str(err) )
            return False

    def waitForNotification(self,timeout):
        self._handler.join(timeout)

    def handleNotification(self,handle,data):
        print("Notification data",data)

    def fromScanData(self,scan_entry):
        # decode the scan data and initialize the object
        for (adType,desc,value) in scan_entry.getScanData():
            if adType== 0x09 :
                self._name=value
            elif adType== 0x16 :
                # print(value)
                service_id= int(value[0:2],16)+int(value[2:4],16)*256
                if self._service_data == None :
                   self._service_data={}
                # print("service id=",hex(service_id))
                self._service_data[service_id]=BLE_DataService.decode(service_id,value[4:])

            elif adType == 0xFF :
                # print("Manufacturing raw data=",value)
                self._mfgID= int(value[0:2],16)+int(value[2:4],16)*256
                self._mfg_data=value[4:]

        self._rssi = scan_entry.rssi
        self._connectable = scan_entry.connectable
        self._interface= scan_entry.iface

    def isConnectable(self):
        return self._connectable

    def printDef(self):
        print ("Name:",self._name," @:",self._addr," RSSI:",self._rssi,"connectable:",self._connectable)

    def printData(self):
        if self._service_data != None :
            for sd in self._service_data.items() :
                print("UUID 0x%4X " % sd[0],"value:",sd[1])


    def printFull(self):
        self.printDef()
        self.printData()
        if self._services != None :
            print ("Services")
            for s in self._services :
                print (s.uuid.getCommonName())
            print ("Characteristics")
            for c in self._channels.values() :
                print (c.uuidName())

    def channel(self,uuid):
        return self._channels[uuid]

    def name(self):
        return self._name

    def getServiceData(self,id) :
        if self._service_data != None :
            try:
                value=self._service_data[id]
                return value
            except  KeyError:
                return None
        else:
            return None

class BLE_Service_Delegate(DefaultDelegate)  :
    def __init__(self,service):
        DefaultDelegate.__init__(self)
        self._service=service

    def handleDiscovery(self, scan_data, isNewDev, isNewData):
        if isNewDev:
            blelog.debug ("BLE scan Discovered device " + str( scan_data.addr)+" "+str(scan_data.addrType))
            self._service.addDevice(scan_data)
        elif isNewData:
            blelog.debug("BLE scan Received new data from "+ str(scan_data.addr))
            dev=self._service.getDevice(scan_data.addr)
            if dev != None :
                dev.fromScanData(scan_data)



class BLE_Device_Delegate(DefaultDelegate):
    def __init__(self,device):
        DefaultDelegate.__init__(self)
        self._device=device

    def handleNotification(self,handle,data):
        self._device.handleNotification(handle,data)

class BLE_Service:
    """
    Main class to access the BLE service
    """

    def __init__(self,interface):
        self._devices={}
        self._filters=[]
        self._detectedDevices=0
        self._scanner= Scanner(interface).withDelegate(BLE_Service_Delegate(self))

    def scan(self,timeout) :
        blelog.info("BLE Scan start for:"+str(timeout)+" sec")
        self._devices={}
        self._detectedDevices=0
        self._scanner.scan(timeout)
        blelog.info("BLE Scan end - nb of devices detected:"+str(self._detectedDevices)+" valid devices:"+str(len(self._devices)))

    def addDevice(self,scan_entry):
        self._detectedDevices = self._detectedDevices + 1
        if self.checkDevice(scan_entry):
            dev=  BLE_Device(scan_entry)
            dev.fromScanData(scan_entry)
            self._devices[scan_entry.addr] = dev
        else:
            blelog.debug("BLE scan filter Device filtered out "+str(scan_entry.addr))

    def getDevices(self):
        return self._devices.values()

    def getDevice(self, addr) :
        try:
            return self._devices[addr]
        except KeyError :
            blelog.debug("BLE device not found: "+str(addr))
            return None

    def nbDevices(self):
        return len(self._devices)

    def nbDetectedDevices(self):
        return self._detectedDevices

    def addFilter(self,filter):
        self._filters.append(filter)

    def checkDevice(self,scan_data):
        for f in self._filters :
            if f.inFilter(scan_data): continue
            else:
                return False
        return True

    def  updateDevice(self,scan_data):
        try:
            dev=self._devices[scan_data.addr]
        except KeyError :
            return
        dev.fromScanData[scan_data]

class BLE_Filter:
    """
    Generic superclass for BLE scan filters
    """

    def inFilter(self,scan_data) :
        blelog.error("BLE scan filter shall be implemented in subclass")
        return False

class BLE_Filter_RSSI(BLE_Filter) :

    def __init__(self,min_rssi):
        self._min_rssi=min_rssi

    def inFilter(self,scan_data):
        return scan_data.rssi >= self._min_rssi

class BLE_Filter_Connectable(BLE_Filter):

    def __init__(self,indicator):
        self._indicator=indicator

    def inFilter(self,scan_data):
        return scan_data.connectable == self._indicator

class BLE_Filter_Whitelist(BLE_Filter):
    """
    Filter a list of MAC addresses
    """

    def __init__(self,address_list=None) :
        self._auth_addresses=[]
        if address_list != None :
            for a in address_list:
                self._auth_addresses.append(a)

    def inFilter(self,scan_data):
        return scan_data.addr in self._auth_addresses

    def addAddress(self,address) :
        self._auth_addresses.append(address)

    def removeAddress(self,address)  :
        try:
            self._auth_addresses.remove(address)
        except ValueError:
            pass

class BLE_Filter_NameStart(BLE_Filter) :
    """"
    Filter object with name starting with pattern
    """

    def __init__(self,pattern) :
        self._pattern=pattern

    def inFilter(self,scan_data) :
        for (adType,desc,value) in scan_data.getScanData():
            if adType== 0x09 :
                if value.startswith(self._pattern)  :
                    return True
        return False

class BLE_Notification_Handler(threading.Thread) :

    def __init__(self,device):
        threading.Thread.__init__(self)
        self._device=device

    def run(self):
        self._device._waitForNotification(10.0)
        self.join()

