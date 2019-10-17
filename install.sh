#!/bin/bash
#
#  script to install ble MQTT Gateway service on solidsense
#
echo " Installing the BLE MQTT Service"

FNAME=BLE_MQTT_Service
DIR=/data/solidsense/ble_gateway

echo "installing the packages"
python3 -m pip install paho-mqtt pyyaml

mkdir $DIR
chmod a+rw $DIR
cp MQTT-Transport-Client/settings_example.cfg $DIR/bleTransport.service.cfg
echo "starting the service BLE MQTT transport"
cp Install/bleTransport.service /etc/systemd/system
chmod 644 /etc/systemd/system/bleTransport.service
# systemctl enable bleTransport.service
systemctl daemon-reload
systemctl status bleTransport

echo "installing the Kura configuration package"
service kura stop

cp Install/BLEConfigurationService.dp /opt/eclipse/kura/data/packages/
echo "BLEConfigurationService=file\:/opt/eclipse/kura/data/packages/BLEConfigurationService.dp" >> /opt/eclipse/kura/data/dpa.properties
service kura start
