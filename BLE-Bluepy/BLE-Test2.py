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

# import bluepy

from BLE_Client import *
from BLE_Data import *

logging.basicConfig(level=logging.DEBUG,stream=sys.stdout,format='%(asctime)s - %(message)s')
logger=logging.getLogger("BLE_Service")

class TestCallback(BLE_Service_Callbacks) :

    def advertisementCallback(self,dev):
        print ("Advertisement Callback received for:",dev.name())

def main():

    BLE_init_parameters()
    level=getLogLevel()
    print("Logging level=",level)
    registerDataServices() # register the services to decode the advertisement
    service=BLE_Service() #  create the BLE interface service
    #service.addFilter(BLE_Filter_Connectable(True))  # filter only connectable devices
    #service.addFilter(BLE_Filter_RSSI(-95))    # filter devices with RSSI higher than -90dB
    #service.addFilter(BLE_Filter_NameStart("C "))  # filter devices with name starting with "C "
    service.scanSynch(15.0,False)  # scan for BLE devices
    devices = service.getDevices() # get all valid devices
    # temp_id=BLE_DataService.getIdFromName('Temperature')
    for dev in devices :
        dev.printDef()



if __name__ == '__main__':
    main()





