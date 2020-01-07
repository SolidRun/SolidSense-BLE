# -*- coding: UTF-8 -*-
#-------------------------------------------------------------------------------
# Name:        BLE MQTT TRansport client - bleTransport service
# Purpose:     Main for the bleTransport servcice - handle MQTT communication
#               and interface towards the BLE Client
#
# Author:      Nicolas Albarel / Laurent Carré
#
# Created:     14/07/2019
# Copyright:   (c) Laurent Carré - Sterwen Technology 2019
# Licence:     Eclipse 1.0
#-------------------------------------------------------------------------------

# update path to include BLE directory
import os, sys, inspect
cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0], "../BLE-Bluepy")))
sys.path.insert(0, cmd_subfolder)



import logging
import json
import os

from time import time
from uuid import getnode
from threading import Thread, Semaphore

from mqtt_wrapper import MQTTWrapper
from utils import ParserHelper
from utils import LoggerHelper

import BLE_Client
import BLE_Data

import argparse
import socket


ble_mqtt_version="1.0.4"
# Global logger
_logger = None

####################################################################
# BLEMQTTService

class BLEMQTTService(BLE_Client.BLE_Service_Callbacks):
    """
    """

    def __init__(self, settings, logger=None, **kwargs):
        super().__init__()

        self.logger = logger or logging.getLogger(__name__)
        self.exitSem = Semaphore(0)

        self.gw_id = settings.gateway_id
        self.gw_model = settings.gateway_model
        self.gw_version = settings.gateway_version

        self.ble_filters = settings.ble_filters
        self.ble_scan = settings.ble_scan

        self.mqtt_wrapper = MQTTWrapper(
            settings,
            self.logger,
            self._on_mqtt_wrapper_termination_cb,
            self._on_connect
        )

        self.mqtt_wrapper.start()
        self.logger.info("Gateway version %s started with id: %s", ble_mqtt_version, self.gw_id)

        self.first_connection = True


    def _on_mqtt_wrapper_termination_cb(self):
        """
        Callback used to be informed when the MQTT wrapper has exited
        It is not a normal situation and better to exit the program
        to have a change to restart from a clean session
        """
        self.logger.error("MQTT wrapper ends. Terminate the program")
        self.exitSem.release()


    def _on_connect(self):
        self.logger.info("MQTT connected!")

        # Suscribe topics
        self.mqtt_wrapper.subscribe("scan/" + self.gw_id, self._scan_cmd_received)
        self.mqtt_wrapper.subscribe("filter/" + self.gw_id, self._filter_cmd_received)
        self.mqtt_wrapper.subscribe("gatt/" + self.gw_id + "/+", self._gatt_cmd_received)

        if self.first_connection:
            self.first_connection = False

            # Init BLE
            BLE_Data.registerDataServices()
            self.service = BLE_Client.BLE_Service()
            self.service.setCallbacks(self)

            # Default configuration
            if len(self.ble_filters) > 0:
                self.logger.info("apply default filters configuration : " + self.ble_filters)
                self._filter_cmd_procesing(self.ble_filters)

            if len(self.ble_scan) > 0:
                self.logger.info("apply default scan configuration : " + self.ble_scan)
                self._scan_cmd_processing(self.ble_scan)


    def deferred_thread(fn):
        """
        Decorator to handle a request on its own Thread
        to avoid blocking the calling Thread on I/O.
        It creates a new Thread but it shouldn't impact the performances
        as requests are not supposed to be really frequent (few per seconds)
        """

        def wrapper(*args, **kwargs):
            thread = Thread(target=fn, args=args, kwargs=kwargs)
            thread.start()
            return thread

        return wrapper


    def catchall(fn):
        """
        Decorator to catch all the errors comming from the callback to protect the calling thread
        """

        def wrapper(*args, **kwargs):
            try:
                fn(*args, **kwargs)
            except Exception as e:
                _logger.exception(" Uncaught exception -> ")

        return wrapper


    def run(self):
        # Nothing to do on the main thread - Just wait the end of the MQTT connection
        self.exitSem.acquire()



    def _checkBadParams(self, payload, typeArgs, mandatoryArgs):
        for param in payload:
            if not param in typeArgs:
                self.logger.info("bad param, not in list :" + param)
                return True

            pType, pValues = typeArgs[param]
            aVal = payload[param]

            if not isinstance(aVal, pType):
                self.logger.info("bad type for " + str(aVal))
                return True

            if not (pValues is None or aVal in pValues):
                self.logger.info("bad value for " + str(aVal))
                return True


        for param in mandatoryArgs:
            if param not in payload:
                self.logger.info("param is missing " + param)
                return True

        return False

    ####################################################################
    # BLE Callbacks
    def publishAdvertisement(self,dev,sub_topic,payload):
        topic="advertisement/"+self.gw_id+"/"+str(dev.address())
        if sub_topic != None :
            topic += "/"+sub_topic
        self.mqtt_wrapper.publish(topic,json.dumps(payload))

    def advertisementCallback(self, dev):
        self.logger.info("Advertisement Callback received for:" + str(dev.name()))


        if self.sub_topics :
        # Print debug informations
            sub_topic=None
            out={}
            if dev.isEddystone() :
                #data=dev.EddystoneFrame()
                dev.eddystoneDict(out)
                self.logger.info("Eddystone beacon:" + str(out))
                sub_topic="eddystone"
                self.publishAdvertisement(dev,sub_topic,out)
            elif dev.isiBeacon():
                dev.iBeaconDict(out)
                self.logger.info("IBeacon UUID:" + str(out))
                sub_topic="ibeacon"
                self.publishAdvertisement(dev,sub_topic,out)
            else:
                sdl = dev.getServiceData()
                if sdl != None :
                    # print("Subtopic publish nb:",len(sdl))
                    for sd in sdl :
                        out.clear()
                        sub_topic=sd.name()
                        out['timestamp'] = dev.getAdvTS()
                        out['type']=sd.type()
                        out['value']=sd.value()
                        self.publishAdvertisement(dev,sub_topic,out)



        out = {}

        if self.scanAdv == 'min':
            dev.minDict(out)
        elif self.scanAdv == 'full':
            dev.fullDict(out)
        else:
            return
        self.logger.debug(out)
        # send Data
        self.publishAdvertisement(dev,None,out)


    def scanEndCallback(self, service):
        self.logger.info("Scan finished")
        out = {}

        if self.scanResult == 'summary':
            service.summaryDict(out)
        elif self.scanResult == 'devices':
            service.summaryDict(out)
            service.devicesDict(out)
        else:
            return

        # Print debug informations
        self.logger.debug(out)

        # send Data
        self.mqtt_wrapper.publish("scan_result/"+self.gw_id, json.dumps(out))

    def notificationCallback(self,notification):
        out={}
        notification.fillDict(out)
        self.logger.debug(out)
        self.mqtt_wrapper.publish("gatt_result/"+self.gw_id+"/"+notification.addr(),json.dumps(out))

    ####################################################################
    # Topic processing
    @staticmethod
    def addrFromTopic(topic):
        """
        extract the address of the device that shall be the last in the topic chain
        """
        elem=topic.split('/')
        last=len(elem)-1
        addr=elem[last]
        # check consistency
        if len(addr) != 17 :   # 6x2 Hex digits + 5 colon
            return None
        # further tests to be implemented
        return addr.lower()



    ####################################################################
    # MQTT Callbacks
    def _scan_cmd_received(self, client, userdata, message):
        payload = message.payload.decode("utf-8")
        self.logger.info("scan request : " + payload)
        self._scan_cmd_processing(payload)

    def _filter_cmd_received(self, client, userdata, message):
        payload = message.payload.decode("utf-8")
        self.logger.info("filter request : " + payload)
        self._filter_cmd_procesing(payload)

    def _gatt_cmd_received(self, client, userdata, message):
        payload = message.payload.decode("utf-8")
        self.logger.info("gatt request : " + message.topic+" : "+payload)
        self._gatt_cmd_processing(message.topic,payload)



    ####################################################################
    # JSON Processing

    @catchall
    def _scan_cmd_processing(self, message):
        try:
            payload = json.loads(message)

        except ValueError as e:
            self.logger.error("Bad scan request ->" + str(e))
            return

        typeArgs = {
            'command' : (str, ['start', 'stop', 'time_scan']),
            'timeout' : ((float, int), None),
            'period'  : ((float, int), None),
            'result'  : (str, ['none', 'summary', 'devices']),
            'advertisement'  : (str, ['none', 'min', 'full']),
            'sub_topics'  : (bool, None),
            'adv_interval'  : ((float, int), None),
        }

        mandatoryArgs = [
            'command',
        ]

        # Check parameters validity
        if self._checkBadParams(payload, typeArgs, mandatoryArgs):
            self.logger.error("Abort scan request")
            return

        # Check also that data_service is an array of string
        if isinstance(payload.get('data_service', None), list):
            for item in payload['data_service']:
                if not isinstance(item, str):
                    self.logger.error("Abort scan request - data_service is not a list of string")

        # Set parameters
        self.setReportingInterval(payload.get('adv_interval', 0))
        self.scanResult = payload.get('result', 'summary')
        self.scanAdv = payload.get('advertisement', 'min')
        scanTimeout = payload.get('timeout', 10.0)
        period = payload.get('period',0)
        self.sub_topics= payload.get('sub_topics',False)

        # Execute the commmand
        scanCmd = payload['command']
        if scanCmd == 'time_scan':
            if period == 0 :
                self.service.scanAsynch(scanTimeout, True)
            else:
                self.service.startPeriodicScan(scanTimeout,period)
        elif scanCmd == 'start':
            self.service.startScan(True)
        elif scanCmd == "stop":
            self.service.stopScan()


    @catchall
    def _filter_cmd_procesing(self, message):
        try:
            payload = json.loads(message)

        except ValueError as e:
            self.logger.error("Bad Filter request ->" + str(e))
            return

        typeArgs = {
            'type' : (str, ['rssi', 'white_list', 'connectable', 'starts_with', 'mfg_id_eq', 'none']),
            'min_rssi' : (int, None),
            'match_string' : (str, None),
            'addresses'  : (list, None),
            'connectable_flag' : (bool, [True, False]),
            'mfg_id'  : (int, None),
        }

        mandatoryArgs = [
            'type',
        ]

        requiredArgs = {
            'rssi' : 'min_rssi',
            'white_list' : 'addresses',
            'connectable' : 'connectable_flag',
            'starts_with' : 'match_string',
            'mfg_id_eq' : 'mfg_id',
        }

        # Check parameters validity
        if isinstance(payload, list):
            for payloadItem in payload:
                self.logger.info("check filter : " + str(payloadItem))
                if self._checkBadParams(payloadItem, typeArgs, mandatoryArgs):
                    self.logger.error("Abort Filter request")
                    return
                elif payloadItem['type'] == 'none' :
                    break
                elif payloadItem.get(requiredArgs[payloadItem['type']], None) is None:
                    self.logger.error("Abort Filter request : missing parameter " + requiredArgs[payloadItem['type']])
                    return
        else:
            self.logger.error("Abort Filter request: request is not a list!")
            return

        # Create Filters and add them to the service
        self.service.clearFilters()

        for payloadItem in payload:
            filterType = payloadItem['type']
            if filterType == 'rssi':
                filter = BLE_Client.BLE_Filter_RSSI(payloadItem['min_rssi'])
            elif filterType == 'white_list':
                filter = BLE_Client.BLE_Filter_Whitelist(payloadItem['addresses'])
            elif filterType == 'connectable':
                filter = BLE_Client.BLE_Filter_Connectable(payloadItem['connectable_flag'])
            elif filterType == 'starts_with':
                filter = BLE_Client.BLE_Filter_NameStart(payloadItem['match_string'])
            elif filterType == 'mfg_id_eq':
                filter = BLE_Client.BLE_Filter_MfgID(payloadItem['mfg_id'])
            elif filterType == 'none':
                break

            self.service.addFilter(filter)


    @catchall
    def _gatt_cmd_processing(self,topic,message):

        try:
            payload = json.loads(message)

        except ValueError as e:
            self.logger.error("Bad GATT request ->" + str(e))
            return

        typeArgs = {
            'command' : (str, ['read', 'write', 'discover','allow_notifications']),
            'transac_id' : ( int, None),
            'bond'  : (bool, None),
            'keep'  : (float, None),
            'characteristic'  : (str, None),
            'service': (str,None),
            'properties': (bool, None),
            'type'  : (int, None),
            'value'  : ((float, int, str), None),
            'action_set' : (list,None)
        }

        mandatoryArgs = [
            'command',
        ]

        # print ("topic:",topic)
        # Check parameters validity
        if self._checkBadParams(payload, typeArgs, mandatoryArgs):
            self.logger.error("Abort GATT request")
            return
        addr=BLEMQTTService.addrFromTopic(topic)
        if addr == None :
            self.logger.error("Abort GATT request - invalid address")
            return

        gattCmd=payload['command']
        transac_id=payload.get('transac_id',None)
        keep=payload.get('keep',0.0)
        service=payload.get('service',None)
        out=None
        error=0
        if gattCmd == 'discover' :
            properties=payload.get('properties',False)
            out={}
            dev=self.service.devGATTDiscover(addr, keep, service,out,properties)
            if dev == None :
                self.logger.error("GATT Discovery error on:" + addr)
                error = 3

        else:
            action_set=payload.get('action_set',None)
            actions=[]
            # self.logger.info("GATT "+gattCmd+" Request on device:"+addr)
            if action_set == None :
                action_a = self.buildAction(payload)
                if action_a != None :
                    actions.append(action_a)

            else:
                for action in action_set :
                    action_a = self.buildAction(action)
                    if action_a != None :
                        actions.append(action_a)

            if error == 0 and len(actions) > 0:
                # yes we have something to do
                out={}
                if gattCmd == 'read' :
                    error = self.cmdGATTread(addr,actions,keep,out)
                elif gattCmd == 'write':
                    error=self.cmdGATTwrite(addr,actions,keep,out)
                elif gattCmd == 'allow_notifications':
                    error=self.cmdGATTallowNotifications(addr,actions,keep,out)

        result=self.buildGATTresponse(gattCmd,error,transac_id,out)
        self.logger.debug("Publish GATT request result:"+result)
        self.mqtt_wrapper.publish("gatt_result/"+self.gw_id+"/"+addr,result)


    def buildAction(self,pd):
        res=[]
        c=pd.get('characteristic',None)
        if c == None : return None
        res.append(c)
        res.append(pd.get('type',BLE_Data.BLE_DataService.BTRAW))
        v= pd.get('value',None)
        if v != None :
            res.append(v)
        return res

    def cmdGATTread(self,addr,actions,keep,out):
        self.logger.debug("GATT read on:"+addr+" #actions:"+str(len(actions)))
        try:
            return self.service.readCharacteristics(addr,actions,keep,out)
        except BLE_Client.BLE_ServiceException as err:
            return 4

    def cmdGATTwrite(self,addr,actions,keep,out):
        self.logger.debug("GATT write on:"+addr+" #actions:"+str(len(actions)))
        try:
            return self.service.writeCharacteristics(addr,actions,keep,out)
        except BLE_Client.BLE_ServiceException as err:
            return 4

    def cmdGATTallowNotifications(self,addr,actions,keep,out) :
        self.logger.debug("GATT allow notifications on:"+addr+" #actions:"+str(len(actions)))
        try:
            return self.service.allowNotifications(addr,actions,keep,out)
        except BLE_Client.BLE_ServiceException as err:
            return 4


    def buildGATTresponse(self, command,  error, transac_id, result):
        out = {}
        out['command'] = command
        out['error'] = error
        if transac_id is not None :
            out['transac_id']=transac_id

        if error == 0 and result != None:
            out['result'] = result

        return json.dumps(out)




####################################################################
# Main function & arguments parsing

class BLEParserHelper(ParserHelper):
    def __init__(
            self,
            description="argument parser",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            version=None,
        ):

        super().__init__(description, formatter_class, version)

    def init_config(self):
        self.add_file_settings()
        self.add_mqtt()
        self.add_gateway_config()
        self.add_ble_config()


    def add_ble_config(self):
        self.ble.add_argument(
            "--ble_filters",
            default=None,
            help=("The list of filters that will be enabled at the service startup, in the JSON format"),
        )

        self.ble.add_argument(
            "--ble_scan",
            default=None,
            help=("The scan command that will be executed at the service startup, in the JSON format"),
        )


def _check_parameters(settings, logger):
    if settings.mqtt_force_unsecure and settings.mqtt_certfile:
        # If tls cert file is provided, unsecure authentication cannot
        # be set
        logger.error("Cannot give certfile and disable secure authentication")
        exit()



def main():
    """
        Main service for transport module

    """

    global _logger

    parse = BLEParserHelper(
        description="BLE Transport service arguments",
    )
    parse.init_config()

    settings = parse.settings()
    if settings.gateway_id is None:
        settings.gateway_id = socket.gethostname()



    log = LoggerHelper(module_name="BLEService", level='error')
    _logger = log.setup()
    BLE_Client.BLE_init_parameters()
    # Set debug level
    _logger.setLevel(BLE_Client.getLogLevel())
    # Override BLE_CLient logger to get logs with the same format
    BLE_Client.blelog = _logger

    _check_parameters(settings, _logger)

    try:
        BLEMQTTService(settings=settings, logger=_logger).run()
    except ConnectionRefusedError as cre:
        _logger.error("Connection refused, try later...")
    except Exception as e:
        _logger.exception(" Uncaught exception (Main Thread) -> ")


if __name__ == "__main__":
    main()
