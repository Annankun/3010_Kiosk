import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from gpiozero import PWMOutputDevice, DistanceSensor
from sense_hat import SenseHat

print("\n[SYSTEM] Initializing SouperComputer Garnish Node...")

# --- HARDWARE CONFIGURATION ---
# We use gpiozero to prevent 'GPIO not allocated' errors on Bookworm OS
# PINOUT:
# Ultrasonic Echo: GPIO 17 (Physical Pin 11) - *Must have voltage divider!*
# Ultrasonic Trig: GPIO 4  (Physical Pin 7)
# Indexer Servo:   GPIO 27 (Physical Pin 13) - Moved to avoid audio driver conflict
# Door Servo:      GPIO 22 (Physical Pin 15) - Moved to avoid audio driver conflict

try:
    sensor = DistanceSensor(echo=17, trigger=4, max_distance=1.0)
    indexer_servo = PWMOutputDevice(27, frequency=50)
    door_servo = PWMOutputDevice(22, frequency=50)
    sense = SenseHat()
    sense.clear()
except Exception as e:
    print(f"[FATAL ERROR] Hardware setup failed: {e}")
    exit(1)

BOWL_THRESHOLD_CM = 10.0

# --- FIREBASE SETUP ---
DATABASE_URL = "https://soupercomputer-group-l1g3-default-rtdb.firebaseio.com/"
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

# --- 360 SERVO MATH (0.32s = 360 degrees, so 90 degrees = 0.08s) ---
# Tweak these slightly if friction makes the return journey slower!
TRAVEL_TIMES_FORWARD = {
    "croutons": 0.08,      # Station 1 (90 degrees)
    "green onions": 0.16,  # Station 2 (180 degrees)
    "bacon bits": 0.24     # Station 3 (270 degrees)
}

TRAVEL_TIMES_BACKWARD = {
    "croutons": 0.08,      
    "green onions": 0.16,  
    "bacon bits": 0.24     
}

# --- HELPER FUNCTIONS ---
def spin_360_servo(servo_obj, direction, duration):
    """Spins a continuous rotation servo using gpiozero PWM."""
    if duration <= 0: return
    
    # 0.10 (10%) = Forward, 0.05 (5%) = Backward
    duty_cycle = 0.10 if direction == "fwd" else 0.05
    
    servo_obj.value = duty_cycle
    time.sleep(duration)
    servo_obj.value = 0.0 # Hard stop
    time.sleep(0.2) # Let momentum settle

def dispense_toppings(toppings_list):
    """
    Mechanical Sequence:
    1. Spin indexer FWD to the topping station.
    2. Open hopper door -> Wait -> Close hopper door.
    3. Spin indexer BWD to the Exit Station (0 degrees) to drop into soup.
    """
    print("[ACTION] Starting Dispense Sequence...")
    sense.show_letter("D", text_colour=[0, 0, 255]) 
    
    for topping in toppings_list:
        topping_key = str(topping).lower() 
        
        if topping_key in TRAVEL_TIMES_FORWARD:
            time_fwd = TRAVEL_TIMES_FORWARD[topping_key]
            time_bwd = TRAVEL_TIMES_BACKWARD[topping_key]
            
            print(f"  -> Moving indexer to {topping} ({time_fwd}s)")
            # 1. Move Indexer to Station
            spin_360_servo(indexer_servo, "fwd", time_fwd)
            
            # 2. Open Door to drop topping INTO the indexer hole
            print(f"  -> Opening hopper door...")
            spin_360_servo(door_servo, "fwd", 0.3) # 0.3s open time (TUNE THIS)
            time.sleep(0.5) # Wait for ingredients to fall
            
            # 3. Close Door
            print(f"  -> Closing hopper door...")
            spin_360_servo(door_servo, "bwd", 0.3) # 0.3s close time (TUNE THIS)
            
            # 4. Return Indexer to Exit Station to drop into soup
            print(f"  -> Returning indexer to Exit Drop ({time_bwd}s)")
            spin_360_servo(indexer_servo, "bwd", time_bwd)
            time.sleep(0.5) # Let it fall into the bowl
            
        else:
            print(f"  [WARNING] Kiosk asked for unknown topping: '{topping}'.")

    print("[ACTION] Dispense Sequence Complete.")

# --- MAIN LOOP ---
def main():
    print("--- GARNISH NODE READY ---")
    print("[INFO] Monitoring FIFO Queue at /orders/1")
    
    last_bowl_state = None
    
    # Reset node status on boot
    db.reference('/garnish/status').set("idle")
    db.reference('/garnish/bowl_present').set(False)

    try:
        while True:
            # 1. CONTINUOUS BOWL DETECTION
            # distance is returned in meters by gpiozero, multiply by 100 for cm
            dist_cm = sensor.distance * 100.0 
            is_bowl_present = (dist_cm < BOWL_THRESHOLD_CM)
            
            if is_bowl_present != last_bowl_state:
                print(f"[SENSOR] Bowl Present: {is_bowl_present} (Dist: {dist_cm:.1f}cm)")
                db.reference('/garnish/bowl_present').set(is_bowl_present)
                last_bowl_state = is_bowl_present
                
                if is_bowl_present:
                    sense.set_pixel(7, 0, 0, 255, 0) # Green dot
                else:
                    sense.set_pixel(7, 0, 255, 0, 0) # Red dot

            # 2. FIFO QUEUE LOGIC
            my_status = db.reference('/garnish/status').get()
            mixer_status = db.reference('/mixer/status').get()
            current_order = db.reference('/orders/1').get()

            # Auto-Reset Logic
            if not current_order and my_status != "idle":
                print("[SYSTEM] Order queue empty. Resetting to IDLE.")
                db.reference('/garnish/status').set("idle")
                sense.clear()
                time.sleep(1)
                continue

            # Processing Logic
            if current_order and mixer_status == "complete" and my_status == "idle":
                print("\n[EVENT] Mixer complete. Checking active order (/orders/1)...")
                
                toppings = current_order.get('toppings', [])
                
                if toppings and len(toppings) > 0 and toppings[0] != "":
                    if is_bowl_present:
                        db.reference('/garnish/status').set("dispensing")
                        
                        dispense_toppings(toppings)
                        
                        print("[SUCCESS] Garnish added. Order Complete.")
                        db.reference('/garnish/status').set("complete")
                        sense.show_letter("C", text_colour=[0, 255, 0])
                    else:
                        print("[ERROR] Safety Interlock: No bowl detected!")
                        db.reference('/garnish/status').set("error_no_bowl")
                        sense.show_letter("X", text_colour=[255, 0, 0])
                else:
                    print("[LOGIC] No toppings required. Skipping.")
                    db.reference('/garnish/status').set("complete")
                    sense.show_letter("S", text_colour=[255, 255, 0])

            time.sleep(0.2) # Very fast polling for responsiveness

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Garnish Node...")
    finally:
        indexer_servo.value = 0.0
        door_servo.value = 0.0
        sense.clear()

if __name__ == "__main__":
    main()