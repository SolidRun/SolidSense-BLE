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

logging.basicConfig(level=logging.DEBUG,stream=sys.stdout,format='%(asctime)s - %(message)s')
logger=logging.getLogger("BLE_Service")

def main():

    registerDataServices() # register the services to decode the advertisement
    service=BLE_Service(0) #  create the BLE interface service
    service.addFilter(BLE_Filter_Connectable(True))  # filter only connectable devices
    service.addFilter(BLE_Filter_RSSI(-95))    # filter devices with RSSI higher than -90dB
    service.addFilter(BLE_Filter_NameStart("C "))  # filter devices with name starting with "C "
    service.scan(15.0)  # scan for BLE devices
    devices = service.getDevices() # get all valid devices
    temp_id=BLE_DataService.getIdFromName('Temperature')
    for dev in devices :
        temp = dev.getServiceData(temp_id)
        if temp != None :
            print("Sensor:",dev.name()," Temperature:",temp)



if __name__ == '__main__':
    main()





