import pyrebase
from config import FIREBASE_CONFIG

firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db = firebase.database()

def boiler_handler(msg):
    print("Boiler:", msg["data"])

def mixer_handler(msg):
    print("Mixer:", msg["data"])

def garnish_handler(msg):
    print("Garnish:", msg["data"])

print("Listening to all kitchen nodes...")

stream1 = db.child("boiler").child("status").stream(boiler_handler)
stream2 = db.child("mixer").child("status").stream(mixer_handler)
stream3 = db.child("garnish").child("status").stream(garnish_handler)

try:
    while True:
        pass
except KeyboardInterrupt:
    stream1.close()
    stream2.close()
    stream3.close()
    print("Stopped.")