import pyrebase
import time
import pin_control
import temp_sensor
firebaseConfig = {
	"apiKey": "YOUR_API_KEY",
	"authDomain": "soupercomputer-f0dad.firebaseapp.com",
	"databaseURL": "https://soupercomputer-f0dad-default-rtdb.firebaseio.com",
	"projectId": "soupercomputer-f0dad",
	"storageBucket": "soupercomputer-f0dad.firebasestorage.app",
	"messagingSenderId": "111112419939",
	"appId": "1:111112419939:web:121ce21735c3658a185656"
}

firebase = pyrebase.initialize_app(firebaseConfig)
db = firebase.database()
db.child("orders").remove()

#Top Solenoid, Heating Pad, Temperature Sensor, Buttom Solenoid
pins = [0,0,0,0]



# ----------------------------
# Boiler State
# ----------------------------

current_temp = 0
target_temp = 100



# Initialize boiler status
db.child("boiler").child("status").update({
	"status": "ready",
	"temperature": current_temp,
	"target_temp": target_temp,
	"timestamp": time.time()
})

# ----------------------------
# Heating Function
# ----------------------------
def can_pour:
	current_temp = temp_sensor.read()
	return (db.child("mixer").child(order_id).child("status").get().val() == "complete") && current_temp <= 50


# ----------------------------
# Process Order
# ----------------------------

def process_order(order_id):
	global current_temp

	#print(f"Processing order: {order_id}")

	db.child("boiler").child("status").update({
		"status": "heating",
		"timestamp": time.time()
	})

	# Heat until target reached
	current_temp = temp_sensor.read()
	pin_control.toggle_pin(pins[1])
	while current_temp < target_temp:
		time.sleep(10)
		current_temp = temp_sensor.read()
		db.child("boiler").child("status").update({
			"temperature": current_temp,
			"timestamp": time.time()
		})
	print("Heating Done!")
	pin_control.toggle_pin(pins[1])
	db.child("boiler").child("status").update({
		"status": "idle",
		"timestamp": time.time()
	})

	# Wait for mixer
	while not can_pour:																	:
		time.sleep(10)

	print("Order finished!")
	pin_control.toggle_pin(pins[3])
	time.sleep(5)
	pin_control.toggle_pin(pins[3])
	

	
	db.child("boiler").child("status").update({
	"temperature": current_temp,
	"timestamp": time.time(),
	"status": "complete"
	})	
	

# ----------------------------
# FIFO Order Processing
# ----------------------------

def process_pending_orders():
	orders = db.child("orders").get()


	if not orders.each():
		print("no orders")
		return

	pending_orders = []

	for order in orders.each():
		order_id = order.key()
		status = db.child("orders").child(order_id).child("status").get().val()
		created_at = db.child("orders").child(order_id).child("time_stamp").get().val() or 0
		if status == "pending":
			pending_orders.append((order_id, created_at))
			# FIFO sort
			pending_orders.sort(key=lambda x: x[1])

	for order_id, _ in pending_orders:
		try:
		
			process_order(order_id)

		except Exception as e:
			print(f"Error processing {order_id}: {e}")

# ----------------------------
# Main Loop
# ----------------------------

if __name__ == "__main__":
	for pin in pins:
		pin_control.setup_pin(pin)
	print("Listening for pending orders...")

	while True:
		process_pending_orders()
		time.sleep(5)
