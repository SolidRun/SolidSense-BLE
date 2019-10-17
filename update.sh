#!/bin/bash
#
#  script to install ble MQTT Gateway service on solidsense
#
echo " Updating the BLE MQTT Service"

FNAME=BLE_MQTT_Service
DIR=/data/solidsense

echo "updating the packages"


systemctl status bleTransport
systemctl stop bleTransport

echo "installing the Kura configuration package"
service kura stop

cp Install/BLEConfigurationService.dp /opt/eclipse/kura/data/packages/
# echo "BLEConfigurationService=file\:/opt/eclipse/kura/data/packages/BLEConfigurationService.dp" >> /opt/eclipse/kura/data/dpa.properties
service kura start
systemctl start bleTransport
