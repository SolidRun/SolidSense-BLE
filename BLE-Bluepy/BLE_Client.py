# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:       BLE Service library running on top of Bluepy
# Purpose:
#              Shall run on LInux only
#
# Author:      Laurent Carre
#
# Created:     15/07/2019
# Copyright:   (c) Laurent Carre - Sterwen Technology 2019
# Licence:     Eclipse 1.0
#-------------------------------------------------------------------------------
# update path to include BLE directory
import os, sys, inspect
cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0], "../bluepy")))
sys.path.insert(0, cmd_subfolder)

import datetime
import time
import fileinput
import logging
import threading
from concurrent import futures
import binascii
import struct
import json

import btle
from btle import Scanner, DefaultDelegate, Peripheral, UUID, BTLEException

from BLE_Data import *

blelog=logging.getLogger('BLEService')

class BLE_ServiceException(Exception):
    pass

##########################################################################

BLE_Adv_STANDARD=0
BLE_Adv_EDDYSTONE=1
BLE_Adv_IBEACON=2


class Channel:
    """
    The Channel class implements a communication channel (Characteristic)
    with a BLE device GATT server
    """
    def __init__(self,device,service,char,typeVar=0):
        self._uuid= char.uuid
        self._char=char
        self._device=device
        self._type=typeVar
        self._handle=self._char.getHandle()
        self._descs= None

    def read(self,typeVar):
        """
        Perform a GATT read
        """

        if self._device.connected():
            if self.supportsRead():
                try:
                    val_raw=self._char.read()
                    # print("***************GATT Read: (",len(val_raw),")",type(val_raw)," val:",val_raw)
                except (IOError,BTLEException) as err:
                    blelog.error ("BLE GATT read"+str(err) )
                    return None
                # now let's decode the result
                try:
                    val = BLE_convert(val_raw,typeVar)
                    return val
                except ValueError :
                    blelog.error("BLE GATT read value decode error type:"+str(typeVar)+" ="+str(val_raw))
                    return None
            else:
                blelog.error("BLE GATT Read not supported by:"+self.uuidStr())
                return None
        else:
            blelog.error ("BLE GATT read device not connected")
            return None

    def write(self,data,typeVar):
        """
        Perform a GATT Write
        """
        blelog.debug("BLE GATT WRITE on Channel: "+self.uuidStr()+" Value: "+str(data))
        if self._device. connected():
            if self.supportsWrite() :
                try:
                    if type(data)== str :
                        data=data.encode()
                    self._char.write(data)
                except (IOError,BTLEException) as err:
                    blelog.error("BLE GATT Write"+str(err))
                    raise BLE_ServiceException("BLE GATT Write"+str(err))
            else:
                raise BLE_ServiceException("BLE GATT Write not supported by:"+self.uuidStr())
        else:
            blelog.error ("BLE GATT write device not connected")


    def getDescriptors(self):
        # print("reading the descriptors")
        self._descs=self._char.getDescriptors()

    def writeDesciptor(self,d_uuid,value):
        if self._descs == None:
            self.getDescriptors()
        for d in self._descs :
            if d.uuid() == d_uuid:
                blelog.debug("BLE GATT Write descriptor:"+"0x%04X"%d_uuid+" value:"+str(value))
                try:
                    d.write(value)
                except (IOError,BTLEException) as err:
                    blelog.error("BLE GATT Write descriptor "+"0x%04X"%d_uuid+" :"+str(err))
                    return True
                return False  # no error
        blelog.error("BLE GATT Write descriptor "+"0x%04X"%d_uuid+" Non existant")
        return True

    def readDescriptor(self,d_uuid,typeVar):
        if self._descs == None:
            self.getDescriptors()
        for d in self._descs :
            if d.uuid() == d_uuid:
                try:
                    buf= d.read()
                    blelog.debug("BLE GATT Read descriptor:"+"0x%04X"%d_uuid+" value:"+str(buf))
                except IOError as err:
                    blelog.error("BLE GATT Read descriptor "+"0x%04X"%d_uuid+" :"+str(err))
                    return None
                # now we shall decode the value
                if typeVar == BLE_DataService.INT :
                    if len(buf) == 2:
                        retvalt=struct.unpack('H',buf)
                    elif len(buf) == 4 :
                        retvalt=struct.unpack('L',buf)
                    else:
                        raise ValueError
                    value=retvalt[0]
                else:
                    # default converstion in byte str
                    value=binascii.b2a_hex(buf).decode('utf-8')
                return value
        blelog.error("BLE GATT Read descriptor "+"0x%04X"%d_uuid+" Non existant")
        return None

    def allowNotifications(self):
        if self._char.canNotify():
            value=struct.pack('H',1)
            # print("Notif value=",value)
            if self.writeDesciptor(0x2902,value) :
                raise BLE_ServiceException("BLE GATT Allow exception failed")
        else:
            raise BLE_ServiceException("BLE GATT Characteristic:"+self.uuidStr()+ " Do not support Notifications")

    def stopNotifications(self):
        if self._char.canNotify():
            value=struct.pack('H',0)
            # print("Notif value=",value)
            if self.writeDesciptor(0x2902,value) :
                raise BLE_ServiceException("BLE GATT Stop exception failed")
        else:
            raise BLE_ServiceException("BLE GATT Characteristic:"+self.uuidStr()+ " Do not support Notifications")

    def processNotification(self,data):
        print ("Notification received date len=",len(data)," :",data)
        return BLE_convert(data,self._type)


    def uuidName(self):
        return self._uuid.getCommonName()

    def uuid(self):
        return self._uuid

    def uuidStr(self):
        return self._uuid.bestStr()

    def propertiesString(self):
        return self._char.propertiesToString()

    def handle(self):
        return self._handle

    def setType(self,typeVar):
        self._type=typeVar

    def supportsRead(self):
        return self._char.supportsRead()
    def supportsWrite(self):
        return self._char.supportsWrite()
    def canNotify(self):
        return self._char.canNotify()

################################################################################
#
#    BLE device class
################################################################################

class BLE_Device :
    """
    Proxy for a BLE device with or without GATT server capabilities
    The object is created from a scan entry
    BLE_Device shall be instantiated only by BLE_Service.addDevice()

    """
    def __init__(self,scan_entry,ble_s):
        self._p=None
        self._ble_s=ble_s
        self._connectable=False
        self._connected=False
        self._addr=scan_entry.addr
        self._addrType=  scan_entry.addrType
        self._name=None
        self._flags=0
        self._rssi= -200
        self._services=None
        self._channels=None
        self._service_data=None
        self._adv_time_stamp=0.0
        self._adv_last_report=0.0
        self._mfgID=None
        self._discovered=False
        self._advType=BLE_Adv_STANDARD
        self._notifListener=None
        self._disconnectTimer=None
        self._transacLock=threading.Lock()    # exclusion lock
        self._transacEvent=threading.Event()  # event on transaction
        self._transacEvent.set()

    def initDevConnect(self):
        self._services=None
        self._channels=None
        self._service_data=None
        self._discovered=False
        self._notifListener=None
        self._disconnectTimer=None
        self._transacLock=threading.Lock()    # exclusion lock
        self._transacEvent=threading.Event()  # event on transaction
        self._transacEvent.set()

    def connect(self):
        """
        perform a GATT connect
        Shall not be called directly prefer BLE_Service.devConnect
        """
        if self._name == None :
            dev_name=""
        else:
            dev_name=self._name
        blelog.info ("BLE GATT connecting: "+str(self._addr)+" type "+str(self._addrType)+" Name:"+dev_name)
        if not self._connectable :
            blelog.info("BLE GATT connect : Device is not connectable")
            return False
        if self._p != None :
            # the object has been connected -> reset
            self.initDevConnect()
        if not self.transactionInProgress(False,False):
            self.startTransaction()
        if self._innerConnect():
            self.endTransaction()
            return False
        self._connected=True
        self._connectTS=time.time()
        self._ble_s.devConnected(self)
        # self._allowNotification()
        self.endTransaction()
        blelog.info("BLE GATT device:"+self.name()+" CONNECTED")
        return True

    def _innerConnect(self):
        mtu=getparam('notif_MTU')
        try:
            self._p= Peripheral(self._addr,self._addrType,self._ble_s.ifNumber(),mtu)
            return False    # no error
        except BTLEException as err:
            blelog.error ("BLE GATT Connect: "+str(err))
            return True

    def discover(self,service_uuid=None):
        """
        Perform a GATT discovery and store services and characteristics locally
        set the discovered flag
        return True if the device needs to be disconnected due to failures
        """
        if not self._connected :
            blelog.error("BLE GATT Discover "+self._addr+" disconnected")
            return False


        if type(service_uuid) == type(None):
            try:
                services=self._p.getServices()
            except btle.BTLEException as err:
                blelog.error("BLE GATT Discover "+self._addr+" services:"+str(err))
                return True
            self._services=[]
            for s in services :
                self._services.append(BLE_GATT_Service(s))

        else :
            service_uuid=UUID(service_uuid)
            try:
                service=self._p.getServiceByUUID(service_uuid)
            except btle.BTLEException as err:
                blelog.info("BLE GATT Discover "+self._addr+" UUID:"+str(service_uuid)+" :"+str(err))
                return False
            self._services=[BLE_GATT_Service(service)]

        self._channels={}
        for service in self._services:
            try:
                cl=service.sbpy().getCharacteristics()
            except btle.BTLEException as err:
                blelog.error("BLE GATT Discover "+self._addr+" characteristics:"+str(err))
                return True
            for c in cl :
                st= c.uuid
                c=  Channel(self,service,c)
                self._channels[st]=  c
                service.addCharacteristic(c)

        self._discovered=True
        blelog.debug("BLE GATT "+self._addr+" Discovered")
        return False

    def connected(self):
        return self._connected

    def discovered(self):
        return self._discovered

    def _disconnect(self):
        if self._connected :
            self._p.disconnect()
            self._connected=False

    def disconnect(self):
        if self._connected :
            self.startTransaction()
            blelog.debug("BLE Device "+self.name()+ " Disconnect request")
            if self._disconnectTimer != None:
                self._disconnectTimer.cancel()
            if self._notifListener != None :
                self._notifListener.stopListen()
            # print("*************Actual disconnect for:",self.name())
            self._p.disconnect()
            # print("## Disconnect done wait for listiner to stop")
            if self._notifListener != None :
                self._notifListener.join()
            # print("## Listener stopped")
            self._connected=False
            # self._discovered=False
            self._notifListener=None
            self._disconnectTimer=None
            self._ble_s.devDisconnected(self)
            self.endTransaction()
            blelog.info("BLE GATT device:"+self.name()+" DISCONNECTED")

    def reconnect(self):
        if self._connected :
            return True
        try:
            self._p.connect(self._addr,self._addrType)
        except btle.BTLEException as err:
            blelog.error ("BLE GATT reconnect"+str(err))
            return False
        self._connected=True
        return True

    def allowNotifications(self,channel) :
        # print ("############## Allow notif on Channel:" ,channel.uuidStr())
        if self._notifListener == None:
            self._notifChannels=[]
            # self._p.setMTU(63) #  for ELA tags to be generalized
            self._p.withDelegate(BLE_Device_Delegate(self) )
            self._notifListener=BLE_Notification_Listener(self)
            self._notifListener.start()

        self._notifChannels.append(channel)

    def stopNotifications(self):
        blelog.debug("BLE Device "+self.name()+" Stopping notifications")
        if self._notifListener != None :
            self._notifListener.stopListen()
            self._notifListener.join() # wait for the notification listening thread to stop
            for c in self._notifChannels :
                c.stopNotifications()
            self._notifChannels.clear()
            self._notifListener=None

    def isListeningNotifications(self):
        return self._notifListener != None

    @staticmethod
    def disconnectTimeout(*argv):
        dev=argv[0]
        blelog.debug("BLE Service - Connection duration timer expired:"+dev.name())
        dev._disconnectTimer=None
        if dev.transactionInProgress(False,False):
            # something is running connect or disconnect so don't mess up
            blelog.debug("BLE Service - timer expired while transaction in progress on:"+dev.name())
            return
        dev.disconnect()


    def armDisconnectTimer(self,timeout):
        blelog.debug("BLE Service - Arming connection timer for:"+self.name()+" duration:"+str(timeout))
        if self._disconnectTimer != None :
            self._disconnectTimer.cancel()

        self._disconnectTimer=threading.Timer(timeout,BLE_Device.disconnectTimeout,(self,None))
        self._disconnectTimer.start()

    def stopDisconnectTimer(self):
        if self._disconnectTimer != None :
            self._disconnectTimer.cancel()
            self._disconnectTimer = None

    def handleNotification(self,notification):
        blelog.debug("BLE GATT Notification received on:"+self._addr)
        for channel in self._notifChannels :
            if channel.handle() == notification._handle :
                notification.setChannel(channel)
                self.armDisconnectTimer(10.0)   # to be improved by saving the timeout
                self._ble_s.notificationReceived(notification)
                return
        blelog.error("BLE GATT Notification on:"+self.name()+" Unknown handle:"+str(notification._handle))

    def transactionInProgress(self,wait,lock) :
        # check if there is a long transaction going on
        # return True if a tran is or was in progress
        if self._transacEvent.is_set():
            return False # no transaction in progress
        else:
            if wait:
                self._transacEvent.wait()
            if lock :
                self._transacEvent.clear()
                self._transacLock.acquire()
            return True

    def startTransaction(self):
        self._transacEvent.clear()
        self._transacLock.acquire()

    def endTransaction(self):
        self._transacLock.release()
        self._transacEvent.set()


    def fromScanData(self,scan_entry):
        """
        This method is processing the advertisement frame
        to populate or updated the device
        """
        # update the timestamp
        self._adv_time_stamp= time.time()
        # decode the scan data and initialize the object
        for (adType,desc,value) in scan_entry.getScanData():
            if adType == 0x01 :
                self._flags=int(value,16)
            elif adType == 0x03 :
                # list of 16 bits services
                # nbs= int(len(value) / 4)
                #print("16 bits service type:",type(value))
                # bluepy is returning the full 128 bit string
                service_id= int(value[4:6],16)*256+int(value[6:8],16)
                # print("List of Service ID: %04X"%service_id)
                if service_id == Eddystone.serviceUUID :
                    # print(" Eddystone detected")
                    self._advType=BLE_Adv_EDDYSTONE
            elif adType== 0x09 :
                self._name=value
            elif adType== 0x16 :
                # value can be multiple => treat as a array
                # print("Value=",value,type(value))
                if isinstance(value,dict) :
                    values=value.items()
                else:
                    values=[value]

                for val in values:
                    # print(" Service data:",val)

                    service_id= val[0]
                    if self._service_data == None :
                       self._service_data={}
                    # print("addr:",self._addr,"service id=",hex(service_id))
                    self._service_data[service_id]=BLE_ServiceData(service_id,val[1])
                    # print("addr:",self._addr,"service id=",hex(service_id),"val:",self._service_data[service_id].value())
                    if service_id == Eddystone.serviceUUID :
                        # print(" Eddystone detected (service data)")
                        self._Eddystone_Frame_Type=int(val[:4],16)
                        self._Eddystone_Frame=bytearray.fromhex(val[4:])

            elif adType == 0xFF :
                # print("Manufacturing raw data=",value)
                self._mfgID= int(value[0:2],16)+int(value[2:4],16)*256
                self._mfg_data=value[4:]
                if self._mfgID == iBeacon.Apple_MfgID :
                    # check if we have an iBEACON
                    # print("iBeacon detected")
                    if iBeacon.check(self._mfg_data):
                        self._advType=BLE_Adv_IBEACON
                        self._iBeaconUUID=bytearray.fromhex(self._mfg_data[4:44])
                        self._iBeaconPower=int(self._mfg_data[44:46],16)

        self._rssi = max(scan_entry.rssi,self._rssi) # we keep only the max RSSI over a scan
        self._connectable = scan_entry.connectable
        self._interface= scan_entry.iface

    def isConnectable(self):
        return self._connectable

    def isEddystone(self):
        return self._advType == BLE_Adv_EDDYSTONE

    def isiBeacon(self):
        return self._advType == BLE_Adv_IBEACON

    def EddystoneFrame(self):
        if self.isEddystone() :
            return(self._Eddystone_Frame_Type,self._Eddystone_Frame)
        else:
            return None
    def iBeaconUUID(self):
        if self.isiBeacon() :
            return self._iBeaconUUID
        else:
            return None

    def printDef(self):
        print ("Name:",self._name," @:",self._addr," RSSI:",self._rssi,"connectable:",self._connectable)

    def printData(self):
        if self._service_data != None :
            for sd in self._service_data.items() :
                print("UUID 0x%4X %s" % (sd[0],sd[1].name()),"value:",sd[1].value())


    def printFull(self):
        self.printDef()
        self.printData()
        if self._services != None :
            for s in self._services :
                print ("Service:",s.sbpy().uuid)
                for c in s.getCharacteristicsUUID() :
                    print ("\tCharacteristic:",c)

    def channel(self,uuid):
        try:
            return self._channels[uuid]
        except KeyError :
            return None

    def name(self):
        if self._name != None :
            return self._name
        else:
            return str(self._addr)

    def address(self) :
        return self._addr

    def rssi(self):
        return self._rssi

    def mfgID(self):
        if self._mfgID == None:
            return 0
        else:
            return self._mfgID

    def mfgData(self):
        if self._mfgID == None:
            return None
        else:
            return self._mfg_data

    def getServiceDataValue(self,id) :
        if self._service_data != None :
            try:
                value=self._service_data[id]
                return value
            except  KeyError:
                return None
        else:
            return None

    def getServiceData(self):
        if self._service_data != None :
            return self._service_data.values()
        else:
            return None

    def getAdvTS(self):
        return self._adv_time_stamp
    def getLastReport(self):
        return self._adv_last_report
    def setLastReport(self,ts) :
        self._adv_last_report=ts

    #
    #   methods to build dictionnaries from advertisement data
    #
    def minDict(self,out) :
        """
        fills the out dictionary with the minimum description of the device
        """
        out['local_name']=self.name()
        out['timestamp']=self._adv_time_stamp
        out['rssi']=self._rssi
        out['flags']=self._flags
        out['connectable']=self._connectable

    def fullDict(self,out):
        """
        fills the disctionay with the full description of the device
        """
        self.minDict(out)
        if self._service_data != None :
            nbs=len(self._service_data)
        else:
            nbs=0
        out['service_data']=nbs
        if nbs > 0 :
            sd_array=[]
            for sd in self._service_data.items() :
                sdd={}
                sdd['service_uuid']=UUID(sd[0]).bestStr()
                sdd['type']=sd[1].type()
                sdd['value']=sd[1].value()
                sd_array.append(sdd)
            out['service_data_array']=sd_array
        if self._mfgID != None :
            out['mfg_id']= self._mfgID
            out['mfg_data']=self._mfg_data

    def GATTDict(self,out,properties):

        if not self._discovered :
            return
        s_array=[]
        for s in self._services :
            sd={}
            sd['service_uuid']=s.sbpy().uuid.bestStr()
            ca=s.getCharacteristicsDict(properties)
            sd['characteristics']=ca
            s_array.append(sd)
        out['GATT_Description'] = s_array

    def eddystoneDict(self,out):
        if self.isEddystone():
            out['timestamp']=self._adv_time_stamp
            out['frame_type']=self._Eddystone_Frame_Type
            print("Eddystone frame:",type(self._Eddystone_Frame),self._Eddystone_Frame)

            if self._Eddystone_Frame_Type == Eddystone.URL_Frame:
                out['txpower']=int(self._Eddystone_Frame[0])
                url=Eddystone.decodeURL(self._Eddystone_Frame[1:])
                out['url']=url
            elif self._Eddystone_Frame_Type == Eddystone.UID_Frame:
                out['beacon_id']=binascii.b2a_hex(self._Eddystone_Frame[1:]).decode('utf-8')
                out['txpower']=int(self._Eddystone_Frame[0])
            else:
                out['frame']=binascii.b2a_hex(self._Eddystone_Frame).decode('utf-8')


    def iBeaconDict(self,out):
        if self.isiBeacon():
             out['timestamp']=self._adv_time_stamp
             #print("iBeacon:",type(self._iBeaconUUID),len(self._iBeaconUUID),self._iBeaconUUID)
             #hs=binascii.hexlify(self._iBeaconUUID)
             #print("ibeacon(2):",type(hs),hs,str(hs))
             #print("iBeacon(3) UUID:",iBeacon.strUUID(self._iBeaconUUID[:16]))
             out['uuid']= iBeacon.strUUID(self._iBeaconUUID[:16])
             out['majmin']=binascii.b2a_hex(self._iBeaconUUID[16:]).decode('utf-8')





################################################################################
#
#     BLE GATT service class
################################################################################

class BLE_GATT_Service():
    '''
    This class is just keep the link between Service and Characteristic
    '''
    def __init__(self,s):
        self._UUID=s.uuid
        self._sbpy=s
        self._chars=[]

    def sbpy(self):
        return self._sbpy

    def addCharacteristic(self,char):
        self._chars.append(char)

    def getCharacteristicsDict(self,properties):
        res=[]
        for c in self._chars:
            if properties :
                cd={}
                cd['uuid']=c.uuidStr()
                cd['properties']=c.propertiesString()
                res.append(cd)
            else:
                res.append(c.uuidStr())
        return res

    def getDict(self,properties):
        '''
        returns a dictionary describing the GATT service
        '''
        res={}
        res['service']=self._uuid
        res['characteristics']=self.getCharacteristicsUUID()
        return res


################################################################################
#
#    Classes to handle bluepy call backs
################################################################################

class BLE_Service_Delegate(DefaultDelegate)  :
    """
    This call handles the call back when an advertisement packet is sent
    """
    def __init__(self,service):
        DefaultDelegate.__init__(self)
        self._service=service

    def handleDiscovery(self, scan_data, isNewDev, isNewData):
        if isNewDev:
            blelog.debug ("BLE scan Discovered device " + str( scan_data.addr)+" "+str(scan_data.addrType))
            self._service.addDevice(scan_data)
        elif isNewData:
            blelog.debug("BLE scan Received new data from "+ str(scan_data.addr))
            # check if the device has not been filtered out
            dev=self._service.getDevice(scan_data.addr)
            # then update the data
            if dev != None :
                dev.fromScanData(scan_data)
                if self._service._recheckRSSI:
                    #
                    # let's reevaluate the filter
                    if not self._service._rssiFilter.inFilter(scan_data) :
                        return
                self._service.advCallback(dev)
            elif self._service._recheckRSSI :
                if self._service._rssiFilter.inFilter(scan_data) :
                    blelog.debug("BLE scan device added after RSSI increase")
                    self._service.addDevice(scan_data)



class BLE_Device_Delegate(DefaultDelegate):
    """
    Handle call on notifaction for a device"
    """
    def __init__(self,device):
        DefaultDelegate.__init__(self)
        self._device=device

    def handleNotification(self,handle,data):
        self._device.handleNotification(BLE_Notification(self._device,handle,data))


class BLE_Notification():
    """
    hold the data linked to the notification
    """
    def __init__(self,dev,handle,data):
        self._timestamp=time.time()
        self._dev=dev
        self._handle=handle
        self._data=data

    def setChannel(self,channel):
        self._channel=channel

    def addr(self):
        return self._dev.address()

    def fillDict(self,out):
        out['command']='notification'
        out['characteristic']=str(self._channel.uuid())
        out['type']=self._channel._type
        out['value']= self._channel.processNotification(self._data)
        out['timestamp']=self._timestamp




################################################################################
#
#    BLE Service class
################################################################################
class BLE_Service:
    """
    Main class to access the BLE service

    Version 1.0 Only one HCI interface is managed


    """
    runningService=None

    def __init__(self,interface=None):
        self._devices={}
        self._filters=[]
        self._detectedDevices=0
        self._callbacks=None
        self._connectedDev={}
        # self.scanOn=False
        self._recheckRSSI=False
        self._defaultRetries=1
        self._scanLock=threading.Lock()
        self._scan_run=threading.Event()
        self._connect_lock=threading.Event()
        self._connect_lock.set()
        self._scan_run.set()
        self._scan_start=threading.Event()
        self._periodic=False
        self._scan_error=0
        self._inhibitFilter=False
        self._inhibitCallback=False
        if interface == None :
            self._interface=getparam('interface')
        else:
            self._interface=interface

        if self._interface.startswith('hci'):
            self._ifnum=int(self._interface[3])
        else:
            blelog.critical("BLE interface name invalid:"+self._interface)
            raise BLE_ServiceException("Invalid interface")
        blelog.info("BLE Service starting on "+self._interface)
        self._scanner= Scanner(self._ifnum).withDelegate(BLE_Service_Delegate(self))
        BLE_Service.runningService=self

    def ifNumber(self):
        return self._ifnum

    def scanSynch(self,timeout,forceDisconnect,inhibitFlag=False) :
        """
        Synchonous scan - reset all devices

        if forceDisconnect is True, then all connected devices are disconnected
        else the calling Thread shall wait

        """

        self._initScan()
        if inhibitFlag :
            self._inhibitCallback = True
            self._inhibitFilter=True
        # self._periodic=False
        blelog.info("BLE Synchonous Scan start for:"+str(timeout)+" sec")
        self._checkConnected(forceDisconnect)
        self._startScan(timeout)
        blelog.info("BLE Synchronous Scan end - nb of devices detected:"+str(self._detectedDevices)+" valid devices:"+str(len(self._devices)))
        self._scanEnds(0)
        # reset inibitFlags
        self._inhibitCallback=False
        self._inhibitFilter=False

    def scanAsynchWait(self):
        """
        Block the threadt until the end of the asynchronous scan
        """
        if self.scanOn :
            self._listener.join()

    def scanAsynch(self,timeout,forceDisconnect):
        """
        Start a scan and returns as soon as the scan is started
        """
        self._checkConnected(forceDisconnect)
        self._initScan()
        blelog.info("BLE Asynchonous Scan start for:"+str(timeout)+" sec")

        self._listener=BLE_Listener(self,timeout)
        self._scan_start.clear()
        self._listener.start()
        # the thread shall anyway effectively be blocked until effective start
        self._scan_start.wait()

    def startScan(self,forceDisconnect):
        if self.scanOn() :
            # scan already running
            blelog.info("BLE scan - attempt to start while a scan is running - ignored")
            return
        self._initScan()
        blelog.info("BLE  Scan start no timeout")
        self._checkConnected(forceDisconnect)
        self._listener=BLE_ListenerInd(self,self._scanner)
        self._scan_start.clear()
        self._listener.start()
        # the thread shall anyway effectively be blocked until effective start
        self._scan_start.wait()

    def startPeriodicScan(self,timeout,period) :
        if self._periodic :
            blelog.error("BLE Periodic scan - already running")
            return

        self._periodic=True
        self._timeout=timeout
        self._breathTime = max(0,period-timeout)
        self.scanAsynch(timeout,False)

    @staticmethod
    def periodTime():
        blelog.debug("BLE Periodic scan -- timer lapse")
        BLE_Service.runningService.scanAsynch(BLE_Service.runningService._timeout,False)

    def stopScan(self):
        if self.scanOn():
            self._listener.stop()
        if self._periodic :
            self._periodic=False
            if self._breathTime > 0 :
                self._timer.cancel()

    def _initScan(self) :
        self._scanLock.acquire() # protect the scan only one at a time
        self._scan_error=0
        self._scan_run.clear()
        self._devices.clear()
        self._detectedDevices=0
        self._connectedDev.clear()

    def _startScan(self,timeout):
        self._scan_start.set()
        self._connect_lock.set()
        if timeout <= 0 : return True # if no timeout then scan is not executed here
        try:
            self._scanner.scan(timeout)  ## add error handling
        except btle.BTLEException as err:
            blelog.error("BLE Scan "+str(err))
            return False
        return True

    def scanError(self):
        return self._scan_error

    def _scanEnds(self,error):
        self._scan_end=time.time()
        self._scan_error=error
        if not self._inhibitCallback :
            if self._callbacks != None :
                self._callbacks.scanEndCallback(self)
        self._scan_run.set()
        self._scanLock.release()
        if error != 0:
            # need to check that we are not periodic otherwise that creates a deadlock
            if self._periodic :
                if error != 1 :
                    blelog.info("Periodic Scan stopped on error")
                    self._periodic = False
                    return
            else:
                return
        if self._periodic :
            if self._breathTime == 0 :
                self.scanAsynch(self._timeout,False)
            else:
                blelog.debug("BLE Periodic scan -- Timer started")
                self._timer=threading.Timer(self._breathTime,BLE_Service.periodTime)
                self._timer.start()

    def notificationReceived(self,notification):
        """
        called when a notification is received from a device
        """
        if self._callbacks != None :
            self._callbacks.notificationCallback(notification)
        else:
            blelog.info("BLE GATT Notification => no call back defined")


    def scanEndWait(self):
        """
        blocks until a an on going scan ends
        """
        self._scan_run.wait()

    def scanOn(self):
        return not self._scan_run.is_set()

    def _checkConnected(self,flag):
        #
        # this shall be thread safe
        #
        blelog.debug("BLE Service scan start number of devices connected:"+str(len(self._connectedDev))+" force:"+str(flag))
        if flag :
            for d in self._connectedDev.values() :
                d._disconnect()
            self._connect_lock.set()
        else:
            blelog.debug("BLE Service scan start wait for all device to disconnect")
            self._connect_lock.wait()


    def addDevice(self,scan_entry):
        self._detectedDevices = self._detectedDevices + 1
        if self.checkDevice(scan_entry):
            dev=  BLE_Device(scan_entry,self)
            dev.fromScanData(scan_entry)
            self._devices[scan_entry.addr] = dev
            self.advCallback(dev)
        else:
            blelog.debug("BLE scan filter Device filtered out "+str(scan_entry.addr))

    def getDevices(self):
        """
        returns the list of valid devices(BLE_Device instances)
        """
        return self._devices.values()

    def getDevicesAddr(self):
        """
        returns an array of MAC address (string)
        """
        return self._devices.keys()

    def getDevice(self, addr) :
        """
        returns the device instace for the given MAC address
        None if no device found
        """
        try:
            return self._devices[addr]
        except KeyError :
            blelog.debug("BLE device not found or filtered out: "+str(addr))
            return None

    def nbDevices(self):
        """
        returns the number of valid devices
        """
        return len(self._devices)

    def nbDetectedDevices(self):
        return self._detectedDevices

    def addFilter(self,filter):
        """
        add a filter to the scan filter
        """

        self._filters.append(filter)
        if type(filter) == BLE_Filter_RSSI :
            self._recheckRSSI=True
            self._rssiFilter=filter

    def clearFilters(self):
        """
        remove all the scan filters
        """

        self._filters.clear()
        self._recheckRSSI = False

    def checkDevice(self,scan_data):
        if self._inhibitFilter : return True
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

    def advCallback(self,dev):
        if self._inhibitCallback : return
        if self._callbacks != None :
            self._callbacks._advReceived(dev)

    def setCallbacks(self,callbacks) :
        """
        Set the call back instance (subclass of BLE_Service_Callbacks)
        """
        self._callbacks=callbacks

    def devConnected(self,dev):
        # called from dev.connect()
        if self._connect_lock.is_set() :
            # set the lock to prevent scan when devices are connected
            self._connect_lock.clear()
        self._connectedDev[dev.address()]  =dev
        # blelog.debug("BLE SERVICE Device:"+dev.name()+" Connected!")

    def devDisconnected(self,dev):
        # called for dev.disconnect()
        # print("********* Finalizing disconnection for:",dev.name())
        try:
            del self._connectedDev[dev.address()]
        except KeyError :
            blelog.error("BLE Device:"+dev.name()+" Disconnect Not in connected device list")
            pass
        # print("number of connected device:",len(self._connectedDev))
        if len(self._connectedDev)  == 0 :
            # clear the lock as no more devices are connected
            # print("*************Disconnect clearing the connect lock")
            self._connect_lock.set()
        # blelog.debug("BLE GATT disconnect completed for:"+dev.name())

    def devConnect(self,addr,retry=0,queue=False):
        '''
        connect a device from its MAC address
        '''
        # is there a scan on-going
        if self.scanOn() :
            blelog.debug("BLE Connect attempt while scan is running")
            if queue :
                self.scanEndWait()
            else:
                return None

        # is the device already connected
        try:
            dev=self._connectedDev[addr]
            # now let's check that we don't have a disconnect or other long transaction going on
            # if yes, wait and lock the device
            if not dev.transactionInProgress(True,True) :
                # need to clear the timer
                dev.stopDisconnectTimer()
                return dev # that's OK
        except KeyError:
            pass
        # do we know the device
        try:
            dev=self._devices[addr]
        except KeyError :
            blelog.info("BLE SERVICE (CONNECT) DEVICE "+addr+ " NOT FOUND => SCAN")
            return None
        if not dev.isConnectable() :
            return None

        #
        #  Now really open the connection
        #
        nbAttempt=0
        while True:
            if dev.connect():
                return dev
            elif nbAttempt < retry :
                nbAttempt=nbAttempt +1
            else:
                return None

    def devGATTDiscover(self,addr,keep,service,out,properties):
        '''
        connect and discover the device
        '''
        try:
            dev=self.devConnect(addr,self._defaultRetries)
        except BLE_ServiceException as err:
            blelog.error("BLE GATT Discover ERROR:"+err)
            return None

        if dev != None :
            if dev.isListeningNotifications() :
                blelog.debug("BLE GATT New transaction - stopping notifications")
                dev.stopNotifications()
            if dev.discover(service):
                # we have a problem here
                dev.disconnect()
                return None
            if  keep > 0.0 :
                dev.armDisconnectTimer(keep)
            else:
                dev.disconnect()
            dev.GATTDict(out,properties)
            return dev
        else:
            return None

    def devConnectDiscover(self,addr):
        """
        connect and find the characteristic
        """
        dev=self.devConnect(addr,self._defaultRetries)
        if dev == None :
            raise BLE_ServiceException("BLE Service - Failed to connect to:"+addr)

        if dev.discovered():
            # the device was already known, check that we don't have a running notifications
            if dev.isListeningNotifications() :
                blelog.debug("BLE GATT New transaction - stopping notifications")
                dev.stopNotifications()
        else:
            if dev.discover() :
                dev.disconnect()
                raise BLE_ServiceException("BLE Service - Failed to discover:"+addr)


        return dev

    def readCharacteristics(self,addr,actions,keep,out,service=None):
        try:
            dev=self.devConnectDiscover(addr)
        except BLE_ServiceException as err:
            blelog.error("BLE GATT read ERROR:"+str(err) )
            return 3
        # if  dev is not OK, exception has been raised
        values=[]
        for action in actions:
            channel_uuid=UUID(action[0])
            channel=dev.channel(channel_uuid)
            if channel == None :
                blelog.error("BLE Service - Non existent characteristic:"+action[0].bestStr()+ "on:"+addr)
                continue
            value=channel.read(action[1])
            if value == None :
                blelog.debug("BLE GATT read ERROR "+addr+" / "+channel.uuidStr())
                error=6
            else:
                error=0
                blelog.debug("BLE GATT read "+addr+" / "+channel.uuidStr()+" :"+str(value))
                v={}
                v['characteristic']=channel.uuidStr()
                v['type']=action[1]
                v['value']=value
                values.append(v)

        out['values'] =  values
        if keep > 0.0 :
            dev.armDisconnectTimer(keep)
        else:
            dev.disconnect()
        return error

    def writeCharacteristics(self,addr,actions,keep,out,service=None):
        try:
            dev=self.devConnectDiscover(addr)
        except BLE_ServiceException as err:
            blelog.error("BLE GATT write ERROR:"+str(err) )
            return 3
        # if  dev is not OK, exception has been raised
        values=[]
        for action in actions:
            if len(action) != 3:
                blelog.error("BLE GATT write missing arguments in command")
                continue

            channel_uuid=UUID(action[0])
            channel=dev.channel(channel_uuid)
            if channel == None :
                blelog.error("BLE Service - Non existent characteristic:"+str(action[0])+ "on:"+addr)
                continue
            value=action[2]
            try:
                channel.write(value,action[1])
            except BLE_ServiceException as err:
                blelog.debug("BLE GATT write ERROR "+addr+" / "+channel.uuidStr())
                error=9
                break  # very little chance to have the next working

            error=0
            blelog.debug("BLE GATT write "+addr+" / "+channel.uuidStr()+" :"+str(value))
            v={}
            v['characteristic']=channel.uuidStr()
            # v['type']=action[1]
            # v['value']=value
            values.append(v)

        out['values'] =  values
        if keep > 0.0 :
            dev.armDisconnectTimer(keep)
        else:
            dev.disconnect()
        return error

    def allowNotifications(self,addr,actions,keep,out,service=None):
        try:
            dev=self.devConnectDiscover(addr)
        except BLE_ServiceException as err:
            blelog.error("BLE GATT allow notifications ERROR:"+str(err) )
            return 3
        # if  dev is not OK, exception has been raised
        values=[]
        for action in actions:
            channel_uuid=UUID(action[0])
            channel=dev.channel(channel_uuid)
            if channel == None :
                blelog.error("BLE Service - Non existent characteristic:"+channel_uuid.bestStr()+ "on:"+addr)
                continue
            # first we write the descriptor to allow notifications
            if len(action) <= 2 :
                notifChannel=channel
                try:
                    channel.allowNotifications()
                except BLE_ServiceException as err:
                    blelog.error("BLE GATT allow nofication:"+str(err))
                    error = 11
                    break
                if len(action) == 2 :
                    channel.setType(action[1])
                    # then we setup the device for receiving notifications
                    # at that stage only if there is no write command
                    if len(actions) == 1 :
                        dev.allowNotifications(channel)
            # check if have something to write
            if len(action) == 3:
                # we have a complete tuple so we write
                value=action[2]
                channel.setType(action[1])
                try:
                    channel.write(value,action[1])
                except BLE_ServiceException as err:
                    blelog.debug("BLE GATT write ERROR "+addr+" / "+channel.uuidStr()+":"+str(err))
                    error=9
                    break  # very little chance to have the next working
                # then we shall allow the notifications after the write to avoid mixing up the transactions
                dev.allowNotifications(notifChannel)
                error=0
                blelog.debug("BLE GATT write "+addr+" / "+channel.uuidStr()+" :"+str(value))
                v={}
                v['characteristic']=channel.uuidStr()
                # v['type']=action[1]
                # v['value']=value
                values.append(v)

        out['values'] =  values
        if keep <= 0.0 :
            keep=10.
        dev.armDisconnectTimer(keep)
        return error
    #
    #  result dictionaries building methods
    #
    def summaryDict(self,out):
        """
        fills the out disctionary with device info
        """
        out['timestamp']=self._scan_end
        out['error']=self._scan_error
        out['dev_detected']=self._detectedDevices
        out['dev_selected']=self.nbDevices()

    def devicesDict(self,out):
        """
        fills the out disctionary with device info
        """
        devda=[]
        for dev in self._devices.items():
            devd={}
            devd['address']=dev[0]
            devd['local_name']=dev[1].name()
            devd['rssi']=dev[1].rssi()
            devda.append(devd)
        out['devices']=devda

    def findDeviceByName(self,searchStr):
        for a,d in self._devices.items() :
            if d.name().startswith(searchStr) :
                return a
        return None

################################################################################
#
#   Filtering clases
################################################################################
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
                self._auth_addresses.append(a.lower())  # normalise to lower case

    def inFilter(self,scan_data):
        return scan_data.addr in self._auth_addresses

    def addAddress(self,address) :
        self._auth_addresses.append(address.lower())

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

class BLE_Filter_MfgID(BLE_Filter):
    '''
    Filter object to select a specific Manufacturer ID
    '''
    def __init__(self,id):
        self._id=id
        # convert in 4bytes hexa
        h4b="%04X"%id
        hb=h4b[0:2]
        lb=h4b[2:]
        self._hid=(lb+hb).lower()
        # print("H4B=",h4b,"res=",self._hid)

    def inFilter(self,scan_data):
        for (adType,desc,value) in scan_data.getScanData():
            if adType==0xFF :
                # print("MfgId=",value[:4])
                if value[:4] == self._hid :
                    return True
        return False


################################################################################



class BLE_Service_Callbacks:
    """
    This class is an abstract superclass to handle all action callbacks
    It must me derived for actual operation
    """
    def __init__(self):
        self._adv_report_interval=0

    def setReportingInterval(self,interval):
        self._adv_report_interval=interval

    def _advReceived(self,dev):
        if self._adv_report_interval <= 0:
            self.advertisementCallback(dev)
            dev.setLastReport(dev.getAdvTS())
            blelog.debug("raising adv callback for:"+dev.name())
        elif self._adv_report_interval > 0:
            if (dev.getAdvTS() - dev.getLastReport()) >= self._adv_report_interval :
                dev.setLastReport(dev.getAdvTS())
                self.advertisementCallback(dev)
                blelog.debug("raising adv callback for:"+dev.name())

    def _notifReceived(self,dev,charac,data):
        self.notificationCallback(dev,charac,data)

    def advertisementCallback(self,dev):
        blelog.error("advertisement callback to be implemented in subclass")

    def scanEndCallback(self,service):
        blelog.error("scan end callback to be implemented in subclass")

    def notificationCallback(self,notification):
        blelog.error("notification callback to be implemented in subclass")

################################################################################
#
#   Multi-threading support
################################################################################

class BLE_Listener(threading.Thread):

    def __init__(self,service,timeout) :
        threading.Thread.__init__(self)
        self._service=service
        self._timeout=timeout
        self.name="BLE-Listener"

    def stop(self):
        pass

    def run(self) :
        blelog.debug("BLE Listener - start can for:"+str(self._timeout))
        if self._service._startScan(self._timeout) :
            blelog.debug("BLE Listener - scan end on timeout")
            error=0
        else:
            blelog.error("BLE Scan error")
            error=1
        self._service._scanEnds(error)


class BLE_ListenerInd(threading.Thread) :

    def __init__(self,service,scanner):
        threading.Thread.__init__(self)
        self._service=service
        self._s=scanner
        self.stopFlag=False
        self.name="BLE-Listener-Ind"

    def stop(self):
        self.stopFlag=True

    def run(self):
        self.stopFlag=False
        self._s.clear()
        self._service._startScan(-1)
        try:
            self._s.start()
        except btle.BTLEException as err:
            blelog.error("BLE Start Scan:"+str(err))
            self._service.scanEnds(1)
            return
        while True:
            if self.stopFlag :
                try:
                    self._s.stop()
                except btle.BTLEException as err:
                    blelog.error("BLE Scan process:"+str(err))
                break
            try:
                blelog.debug("BLE scan process event start")
                self._s.process()
            except btle.BTLEException as err:
                blelog.error("BLE Scan process:"+str(err))
                break
        self._service._scanEnds(0)



class BLE_Notification_Listener(threading.Thread) :

    def __init__(self,device):
        threading.Thread.__init__(self)
        self._device=device
        self.name=device.name()
        self._stopFlag=False

    def stopListen(self):
        self._stopFlag=True

    def run(self):
        while True:
            try:
                self._device._p.waitForNotifications(5.0)
            except BTLEException as err:
                blelog.error("BLE GATT wait for notification:"+str(err))
                return
            if self._stopFlag : break


################################################################################
#
#   Execution parameters
blegw_parameters=None

def BLE_init_parameters():
    global blegw_parameters
    dir_h=getDataDir()
    fn=dir_h+'/parameters.json'
    try:
        fp=open(fn,'r')
    except IOError as err:
        blelog.info("Read parameters in:"+fn+" Err:"+str(err))
        #  initilaise with default values
        out={}
        out['max_connect']=10
        out['notif_MTU']=63
        out['debug_bluez']=False
        out['trace']= "info"
        out["interface"]="hci0"
        try:
            fp=open(fn,'w')
        except IOError as err:
             blelog.error("Write parameters in:"+fn+" Err:"+str(err))
             raise
        json.dump(out,fp,indent=1)
        fp.close()
        blegw_parameters=out
        return
    blegw_parameters=json.load(fp)
    try:
        intf=blegw_parameters['interface']
    except KeyError :
        blegw_parameters['interface']="hci0"
    fp.close()

def getparam(name):
    try:
        return blegw_parameters[name]
    except KeyError :
        return None

def getDataDir():
    return "/data/solidsense/ble_gateway"

def buildFileName(param):
    fn=getparam(param)
    return getDataDir()+'/'+fn

debug_level_def={ 'debug':logging.DEBUG, 'info': logging.INFO , 'warning':logging.WARNING, 'error':logging.ERROR, 'critical':logging.CRITICAL}

def getLogLevel():
    try:
        level_str= blegw_parameters['trace']
    except KeyError :
        return logging.DEBUG
    level_str=level_str.lower()
    try:
        level=debug_level_def[level_str]
    except KeyError :
        return logging.DEBUG
    # print("debug:",level_str,level)
    bluez_debug=getparam('debug_bluez')
    if bluez_debug == True :
        btle.Bluepy_debug(True)
    return level
