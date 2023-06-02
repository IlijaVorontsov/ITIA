import paho.mqtt.client as paho

def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))

client = paho.Client()
client.on_message = on_message
client.connect("localhost", 1883)
client.subscribe("test")
client.loop_forever()
client.disconnect()