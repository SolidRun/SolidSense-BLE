# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:       BLE-Test
# Purpose:      Test BLE sensor client side
#               Shall run on LInux only
#
# Author:      Laurent Carré
#
# Created:     09/07/2019
# Copyright:   (c) Sterwen Technology 2019
# Licence:     Eclipse 1.0
#-------------------------------------------------------------------------------


import time
import logging
import sys

import bluepy

from BLE_Client import *
from BLE_Data import *
from Ruuvi import *

logging.basicConfig(level=logging.DEBUG,stream=sys.stdout,format='%(asctime)s - %(message)s')
logger=logging.getLogger("BLE_Service")
addresses=None

class TestCallback(BLE_Service_Callbacks) :

    def __init__(self,adv_out,scan_out):

        BLE_Service_Callbacks.__init__(self)
        self._adv_out=adv_out
        self._scan_out=scan_out

    def advertisementCallback(self,dev):
        print ("Advertisement Callback received for:",dev.name())

    def scanEndCallback(self,service):
        global addresses
        print("Scan finished")
        addresses = service.getDevicesAddr() # get all valid devices
        out={}
        if self._scan_out == 'summary':
            service.summaryDict(out)
        elif self._scan_out == 'devices':
            service.summaryDict(out)
            service.devicesDict(out)
        else:
            return
        print(out)

def main():

    global addresses

    registerDataServices() # register the services to decode the advertisement
    service=BLE_Service() #  create the BLE interface service
    # service.addFilter(BLE_Filter_Connectable(True))  # filter only connectable devices
    # service.addFilter(BLE_Filter_RSSI(-80))    # filter devices with RSSI higher than -90dB
    # service.addFilter(BLE_Filter_NameStart("LCA"))  # filter devices with name starting with "C "
    # service.addFilter(BLE_Filter_MfgID(0x0499))
    # define callback
    cb=TestCallback('min','summary')
    service.setCallbacks(cb)
    # cb.setReportingInterval(3.0)
    service.scanAsynch(20.0,True)  # scan for BLE devices
    service.scanAsynchWait()
    print("restart main thread")
    dev_addr="cb:f6:73:49:5e:fb"
    dev=service.devConnectDiscover(dev_addr)
    if dev == None :
        print("*********Error on connect************")
        return
    print("Connected to:",dev.name())
    c1=dev.channel(NordicSerial.notify_uuid)
    if c1 == None :
        print("Error on characteristic:",NordicSerial.nordicNotify)
        return
    c1.getDescriptors()
    flag=c1.readDescriptor(0x2902,BLE_DataService.INT)
    print("Descriptor value:",flag)
    c1.allowNotifications()
    flag=c1.readDescriptor(0x2902,BLE_DataService.INT)
    print("Descriptor value:",flag)
    dev.disconnect()



if __name__ == '__main__':
    main()





