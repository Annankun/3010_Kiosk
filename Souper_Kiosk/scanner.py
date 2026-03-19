import signal
import sys
import time

import cv2
import pyrebase
import RPi.GPIO as GPIO
from picamera2 import Picamera2
from pyzbar.pyzbar import decode

from config import FIREBASE_CONFIG


GREEN_LED_PIN = 17
RED_LED_PIN = 27
EMERGENCY_PIN = 23
LED_ON_SECONDS = 2.0
SCAN_COOLDOWN_SECONDS = 2.0

firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db = firebase.database()

running = True
last_scanned_key = ""
last_scan_time = 0.0


def setup_gpio() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
    GPIO.setup(RED_LED_PIN, GPIO.OUT)
    GPIO.setup(EMERGENCY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.output(GREEN_LED_PIN, GPIO.LOW)
    GPIO.output(RED_LED_PIN, GPIO.LOW)


def flash_led(pin: int) -> None:
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(LED_ON_SECONDS)
    GPIO.output(pin, GPIO.LOW)


def handle_scan(order_key: str) -> None:
    order_key = order_key.strip()
    if not order_key:
        return

    order = db.child("orders").child(order_key).get().val()
    if order and order.get("status") == "ready":
        db.child("orders").child(order_key).remove()
        print(f"VALID pickup: {order_key} removed")
        flash_led(GREEN_LED_PIN)
        return

    print(f"REJECTED pickup: {order_key}")
    flash_led(RED_LED_PIN)


def should_skip_scan(order_key: str) -> bool:
    global last_scanned_key, last_scan_time

    now = time.time()
    if order_key == last_scanned_key and (now - last_scan_time) < SCAN_COOLDOWN_SECONDS:
        return True

    last_scanned_key = order_key
    last_scan_time = now
    return False


def signal_handler(signum: int, frame) -> None:
    global running
    running = False
    print(f"Received signal {signum}, exiting...")


def main() -> int:
    global running

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    setup_gpio()

    camera = Picamera2()
    camera.configure(camera.create_preview_configuration(main={"format": "RGB888", "size": (1280, 720)}))
    camera.start()

    print("QR scanner started. Press Ctrl+C to stop.")

    try:
        while running:
            frame = camera.capture_array()
            decoded_items = decode(frame)

            cv2.imshow("QR Scanner", frame)

            for item in decoded_items:
                key = item.data.decode("utf-8", errors="ignore")
                if should_skip_scan(key):
                    continue
                print(f"Scanned QR key: {key}")
                handle_scan(key)

            cv2.waitKey(1)
    finally:
        camera.stop()
        cv2.destroyAllWindows()
        GPIO.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
