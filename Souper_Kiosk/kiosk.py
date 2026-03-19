import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

import pyrebase
import RPi.GPIO as GPIO

import db as sqlite_tools
from config import FIREBASE_CONFIG


POLL_INTERVAL_SECONDS = 1.0
EMERGENCY_PIN = 23

firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
firebase_db = firebase.database()

sqlite_conn = sqlite_tools.connect()
sqlite_tools.init_db(sqlite_conn)

component_status: Dict[str, str] = {
    "boiler": "",
    "mixer": "",
    "garnish": "",
}
status_lock = threading.Lock()
status_changed = threading.Event()
running = True
current_order_key: Optional[str] = None


def _status_handler_factory(component: str):
    def handler(msg: Dict[str, Any]) -> None:
        value = msg.get("data")
        if value is None or isinstance(value, dict):
            return

        with status_lock:
            component_status[component] = str(value)
        status_changed.set()
        print(f"[{component}] status => {value}")

    return handler



def reset_component_status() -> None:
    with status_lock:
        for name in ("boiler", "mixer", "garnish"):
            component_status[name] = ""

    # Reset Firebase values so stream re-fires when kitchen writes "complete"
    for name in ("boiler", "mixer", "garnish"):
        firebase_db.child(name).child("status").set("idle")

def all_components_complete() -> bool:
    with status_lock:
        return all(component_status.get(name) == "complete" for name in ("boiler", "mixer", "garnish"))


def normalize_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            return ts / 1000.0
        return ts
    return float("inf")


def to_epoch_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts < 10_000_000_000:
            return int(ts * 1000)
        return int(ts)
    return int(time.time() * 1000)


def get_oldest_pending_order() -> Optional[Tuple[str, Dict[str, Any]]]:
    snapshot = firebase_db.child("orders").get().val() or {}
    pending = []
    for key, order in snapshot.items():
        if not isinstance(order, dict):
            continue
        if order.get("status") != "pending":
            continue
        pending.append((normalize_timestamp(order.get("timestamp")), key, order))

    if not pending:
        return None

    pending.sort(key=lambda item: item[0])
    _, key, order = pending[0]
    return key, order


def sync_inventory_to_firebase() -> None:
    inventory = sqlite_tools.get_inventory(sqlite_conn)
    payload = {item: data["quantity"] for item, data in inventory.items()}
    firebase_db.child("inventory").set(payload)
    print("Inventory synced to Firebase /inventory")


def can_fulfill_order(order: Dict[str, Any]) -> bool:
    inventory = sqlite_tools.get_inventory(sqlite_conn)

    needed: Dict[str, int] = {}
    soup = order.get("soup_type")
    if soup:
        needed[soup] = needed.get(soup, 0) + 1

    for topping in order.get("toppings", []) or []:
        needed[topping] = needed.get(topping, 0) + 1

    for item_name, amount in needed.items():
        current = inventory.get(item_name, {}).get("quantity", 0)
        if current < amount:
            print(f"Insufficient inventory: {item_name} need={amount}, have={current}")
            return False
    return True


def consume_order_inventory(order: Dict[str, Any]) -> None:
    changes: Dict[str, int] = {}
    soup = order.get("soup_type")
    if soup:
        changes[soup] = changes.get(soup, 0) - 1

    for topping in order.get("toppings", []) or []:
        changes[topping] = changes.get(topping, 0) - 1

    sqlite_tools.update_inventory(sqlite_conn, changes)
    sync_inventory_to_firebase()


def mark_order(key: str, status: str) -> None:
    firebase_db.child("orders").child(key).update({"status": status})
    print(f"Order {key} => {status}")


def wait_until_order_deleted(key: str) -> None:
    print(f"Waiting for customer pickup: {key}")
    while running:
        exists = firebase_db.child("orders").child(key).get().val()
        if exists is None:
            print(f"Order {key} picked up and deleted.")
            return
        time.sleep(POLL_INTERVAL_SECONDS)


def save_ready_order_to_sqlite(key: str, order: Dict[str, Any]) -> None:
    sqlite_tools.insert_order(
        sqlite_conn,
        {
            "firebase_key": key,
            "soup_type": order.get("soup_type", ""),
            "toppings": order.get("toppings", []),
            "total": order.get("total", 0.0),
            "status": "ready",
            "timestamp": to_epoch_ms(order.get("timestamp")),
        },
    )
    print(f"Saved ready order to SQLite: {key}")


def process_orders() -> None:
    global current_order_key
    while running:
        next_order = get_oldest_pending_order()
        if not next_order:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        key, order = next_order

        if not can_fulfill_order(order):
            mark_order(key, "cancelled")
            continue

        current_order_key = key
        mark_order(key, "processing")
        reset_component_status()
        consume_order_inventory(order)

        while running:
            if all_components_complete():
                mark_order(key, "ready")
                save_ready_order_to_sqlite(key, order)
                break
            status_changed.wait(timeout=POLL_INTERVAL_SECONDS)
            status_changed.clear()

        if not running:
            break

        wait_until_order_deleted(key)


def handle_emergency(channel: int = None) -> None:
    global running, current_order_key
    print("Emergency stop triggered!")
    if current_order_key:
        mark_order(current_order_key, "cancelled")
    firebase_db.child("system").child("status").set("emergency")
    running = False
    status_changed.set()


def check_and_recover_from_emergency() -> None:
    status = firebase_db.child("system").child("status").get().val()
    if status != "emergency":
        return
    print("Recovering from emergency stop...")
    orders = firebase_db.child("orders").get().val() or {}
    for key, order in orders.items():
        if isinstance(order, dict) and order.get("status") == "processing":
            mark_order(key, "cancelled")
    firebase_db.child("system").child("status").set("online")
    print("Recovery complete. System online.")


def handle_exit(signum: int, frame: Any) -> None:
    global running
    running = False
    status_changed.set()
    print(f"Received signal {signum}, exiting...")


def main() -> int:
    check_and_recover_from_emergency()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(EMERGENCY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.add_event_detect(EMERGENCY_PIN, GPIO.FALLING, callback=handle_emergency, bouncetime=300)

    sync_inventory_to_firebase()

    streams = [
        firebase_db.child("boiler").child("status").stream(_status_handler_factory("boiler")),
        firebase_db.child("mixer").child("status").stream(_status_handler_factory("mixer")),
        firebase_db.child("garnish").child("status").stream(_status_handler_factory("garnish")),
    ]

    print("Kiosk worker started. Waiting for pending orders...")

    try:
        process_orders()
    finally:
        for stream in streams:
            stream.close()
        sqlite_conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
