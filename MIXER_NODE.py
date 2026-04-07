import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from gpiozero import PWMOutputDevice, DigitalOutputDevice
from sense_hat import SenseHat

print("\n[SYSTEM] Initializing SouperComputer Mixer Node...")

# --- HARDWARE CONFIGURATION ---
# IBT-2 BTS7960 H-Bridge motor driver
# RPWM: GPIO 18 (Physical Pin 12) - Forward PWM
# LPWM: GPIO 19 (Physical Pin 35) - Backward PWM
# R_EN: GPIO 23 (Physical Pin 16) - Right/Forward enable
# L_EN: GPIO 24 (Physical Pin 18) - Left/Backward enable

# Servos for Powder Dispenser (Same logic as Garnish Node)
INDEXER_SERVO_PIN = 27  # Physical Pin 13
DOOR_SERVO_PIN = 22     # Physical Pin 15

try:
    # Motor Setup
    motor_rpwm = PWMOutputDevice(18, frequency=300)
    motor_lpwm = PWMOutputDevice(19, frequency=300)
    motor_r_en = DigitalOutputDevice(23)
    motor_l_en = DigitalOutputDevice(24)
    
    # Servo Setup (50Hz for 360 servos)
    indexer_servo = PWMOutputDevice(INDEXER_SERVO_PIN, frequency=50)
    door_servo = PWMOutputDevice(DOOR_SERVO_PIN, frequency=50)
    
    sense = SenseHat()
    sense.clear()
except Exception as e:
    print(f"[FATAL ERROR] Hardware setup failed: {e}")
    exit(1)

# --- MIXER & DISPENSER CONFIGURATION ---
MIX_DURATION_SECONDS = 10.0   # How long to run the mixer (tune this)
MOTOR_SPEED = 0.8             # PWM duty cycle 0.0 - 1.0 (tune this)

# Tweak these calibration times for the Soup Base 3D print!
TRAVEL_TIMES_FORWARD = {
    "tomato": 0.08,      
    "miso": 0.16,  
    "vegetable": 0.24     
}

TRAVEL_TIMES_BACKWARD = {
    "tomato": 0.08,      
    "miso": 0.16,  
    "vegetable": 0.24     
}

# --- FIREBASE SETUP ---
DATABASE_URL = "https://soupercomputer-group-l1g3-default-rtdb.firebaseio.com/"
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})

# --- HELPER FUNCTIONS ---
def motor_forward(speed):
    """Spin motor forward at given speed (0.0 - 1.0)."""
    motor_r_en.on()
    motor_l_en.off()
    motor_rpwm.value = speed
    motor_lpwm.value = 0.0

def motor_stop():
    """Hard stop the motor."""
    motor_rpwm.value = 0.0
    motor_lpwm.value = 0.0
    motor_r_en.off()
    motor_l_en.off()

def run_mixer():
    """Mixing Sequence."""
    print(f"[ACTION] Starting mixer for {MIX_DURATION_SECONDS}s at speed {MOTOR_SPEED}...")

    motor_forward(MOTOR_SPEED/3)
    time.sleep(MIX_DURATION_SECONDS/3)
    motor_forward(2*MOTOR_SPEED/3)
    time.sleep(MIX_DURATION_SECONDS/3)
    motor_forward(MOTOR_SPEED)
    time.sleep(MIX_DURATION_SECONDS/3)
    motor_stop()

    print("[ACTION] Mixing complete. Motor stopped.")

def spin_360_servo(servo_obj, direction, duration):
    """Spins a continuous rotation servo using gpiozero PWM."""
    if duration <= 0: return
    duty_cycle = 0.10 if direction == "fwd" else 0.05
    servo_obj.value = duty_cycle
    time.sleep(duration)
    servo_obj.value = 0.0 # Hard stop
    time.sleep(0.2)

def dispense_soup_base(soup_type):
    """Mechanical Sequence to drop the powder base BEFORE mixing."""
    print(f"[ACTION] Starting Powder Dispense Sequence for: {soup_type}")
    
    soup_key = str(soup_type).lower() 
    
    if soup_key in TRAVEL_TIMES_FORWARD:
        time_fwd = TRAVEL_TIMES_FORWARD[soup_key]
        time_bwd = TRAVEL_TIMES_BACKWARD[soup_key]
        
        print(f"  -> Moving indexer to {soup_type} ({time_fwd}s)")
        spin_360_servo(indexer_servo, "fwd", time_fwd)
        
        print(f"  -> Opening hopper door...")
        spin_360_servo(door_servo, "fwd", 0.3) # Tune open time
        time.sleep(0.5) # Wait for powder to fall
        
        print(f"  -> Closing hopper door...")
        spin_360_servo(door_servo, "bwd", 0.3) # Tune close time
        
        print(f"  -> Returning indexer to Exit Drop ({time_bwd}s)")
        spin_360_servo(indexer_servo, "bwd", time_bwd)
        time.sleep(0.5) 
        
    else:
        print(f"  [WARNING] Kiosk asked for unknown base: '{soup_type}'. Skipping powder.")

    print("[ACTION] Powder Dispense Sequence Complete.")

# --- MAIN LOOP ---
def main():
    print("--- MIXER NODE READY ---")
    print("[INFO] Waiting for boiler_node 'ready' signal at /boiler/status")

    # Reset node status on boot
    db.reference('/mixer/status').set("idle")

    try:
        while True:
            boiler_status = db.reference('/boiler/status').get()
            my_status     = db.reference('/mixer/status').get()
            current_order = db.reference('/orders/1').get()
            bowl_present  = db.reference('/garnish/bowl_present').get()

            # Auto-Reset Logic
            if not current_order and my_status != "idle":
                print("[SYSTEM] Order queue empty. Resetting to IDLE.")
                db.reference('/mixer/status').set("idle")
                sense.clear()
                time.sleep(1)
                continue

            # Processing Logic
            if current_order and boiler_status == "ready" and my_status == "idle":
                print("\n[EVENT] Boiler ready. Checking safety interlocks...")
                
                # GLOBAL SAFETY CHECK (From Laavanya's Garnish Node)
                if not bowl_present:
                    print("[ERROR] Safety Interlock: No bowl detected! Cannot dispense powder.")
                    db.reference('/mixer/status').set("error_no_bowl")
                    sense.show_letter("X", text_colour=[255, 0, 0])
                    time.sleep(2)
                    continue

                print("[EVENT] Bowl is present. Starting powder and mixing sequence...")
                db.reference('/mixer/status').set("mixing")
                sense.show_letter("M", text_colour=[0, 0, 255])

                # 1. DISPENSE POWDER FIRST
                soup_type = current_order.get('soup_type', '')
                if soup_type:
                    dispense_soup_base(soup_type)

                # 2. MIX THE SOUP
                run_mixer()

                # 3. MARK COMPLETE
                print("[SUCCESS] Mixing done. Signalling garnish node.")
                db.reference('/mixer/status').set("complete")
                sense.show_letter("C", text_colour=[0, 255, 0])

            time.sleep(0.2)  # Fast polling for responsiveness

    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Mixer Node...")
    finally:
        motor_stop()
        indexer_servo.value = 0.0
        door_servo.value = 0.0
        sense.clear()

if __name__ == "__main__":
    main()
