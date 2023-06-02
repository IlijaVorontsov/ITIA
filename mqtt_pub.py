import paho.mqtt.client as paho

from time import sleep

client = paho.Client()
client.connect("localhost", 1883)

for i in range (100):
    client.publish(f"telegraf/one/cpu/{i}")
    sleep(1)
client.disconnect()