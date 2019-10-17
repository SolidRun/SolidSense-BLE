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

logging.basicConfig(level=logging.INFO,stream=sys.stdout,format='%(asctime)s - %(message)s')
logger=logging.getLogger("BLE_Service")
addresses=None

class TestCallback(BLE_Service_Callbacks) :

    def __init__(self,adv_out,scan_out):

        BLE_Service_Callbacks.__init__(self)
        self._adv_out=adv_out
        self._scan_out=scan_out

    def advertisementCallback(self,dev):
        print ("Advertisement Callback received for:",dev.name())
        out={}
        if self._adv_out == 'min':
            dev.minDict(out)
        elif self._adv_out == 'full':
            dev.fullDict(out)
            if dev.mfgID() == 0x0499 :
                out['Ruuvi_data'] =RuuviRaw(dev).decode_data()
        if dev.isEddystone() :
            data=dev.EddystoneFrame()
            print("Eddystone frame type:",hex(data[0])," frame:",data[1] )
        elif dev.isiBeacon():
            print("IBeacon UUID:",dev.iBeaconUUID())
        else:
            return

        print(out)

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
    cb.setReportingInterval(3.0)
    nbs=0
    while nbs <2 :
        print("Starting sequence============================")
        service.scanAsynch(40.0,True)  # scan for BLE devices
        service.scanAsynchWait()
        print("restart main thread")
        # addresses = service.getDevicesAddr() # get all valid devices
        # temp_id=BLE_DataService.getIdFromName('Temperature')
        """
        for addr in addresses :

            d=service.devGATTDiscover(addr,True)
            if d != None :
                d.printFull()
                out={}
                d.GATTDict(out)
                print (out)
            else:
                print("Cannot connect to:",addr)
        """
        nbs=nbs+1


if __name__ == '__main__':
    main()





