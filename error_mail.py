import paho.mqtt.client as paho
from email.message import EmailMessage
import ssl
import smtplib


email = 'advancedpythoncourse@gmail.com'
password = ''
email_to = 'ilija.vorontsov@student.tuwien.ac.at'


def send_mail(email_to, email_msg):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(email, password)
        smtp.sendmail(email, email_to, email_msg.as_string())

def on_message(client, userdata, msg):
    email_msg = EmailMessage()
    email_msg['From'] = email
    email_msg['To'] = email_to
    email_msg['Subject'] = '[ITIA] Error in station'

    body = f'''
    An error occured in the MQTT topic {msg.topic}:
    {msg.payload}
    '''

    email_msg.set_content(body)

    send_mail(email_to, email_msg)

client = paho.Client()
client.on_message = on_message
client.connect("128.130.56.9", 49152)
client.subscribe("itia/+/errors/+")
client.loop_forever()
client.disconnect()