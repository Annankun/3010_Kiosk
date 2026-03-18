import pyrebase
import time
from config import FIREBASE_CONFIG

firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db = firebase.database()

order_id = str(int(time.time()))

order = {
    "order_id": order_id,
    "soup_type": "miso",
    "toppings": ["egg"],
    "price": 9.99,
    "status": "pending",
    "timestamp": time.time()
}

db.child("orders").child(order_id).set(order)

print("Order sent:", order_id)