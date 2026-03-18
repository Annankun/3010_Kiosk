import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

import pyrebase

from config import FIREBASE_CONFIG


POLL_INTERVAL_SECONDS = 1.0

firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
db = firebase.database()

component_status: Dict[str, str] = {
    "boiler": "",
    "mixer": "",
    "garnish": "",
}
status_lock = threading.Lock()
status_changed = threading.Event()
running = True


def _status_handler_factory(component: str):
    def handler(msg: Dict[str, Any]) -> None:
        value = msg.get("data")
        if value is None:
            return
        if isinstance(value, dict):
            return
        with status_lock:
            component_status[component] = str(value)
        status_changed.set()
        print(f"[{component}] status => {value}")

    return handler


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


def get_oldest_pending_order() -> Optional[Tuple[str, Dict[str, Any]]]:
    snapshot = db.child("orders").get().val() or {}
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


def mark_order(key: str, status: str) -> None:
    db.child("orders").child(key).update({"status": status})
    print(f"Order {key} => {status}")


def wait_until_order_deleted(key: str) -> None:
    print(f"Waiting for customer pickup: {key}")
    while running:
        exists = db.child("orders").child(key).get().val()
        if exists is None:
            print(f"Order {key} picked up and deleted.")
            return
        time.sleep(POLL_INTERVAL_SECONDS)


def process_orders() -> None:
    while running:
        next_order = get_oldest_pending_order()
        if not next_order:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        key, _ = next_order
        mark_order(key, "processing")

        while running:
            if all_components_complete():
                mark_order(key, "ready")
                break
            status_changed.wait(timeout=POLL_INTERVAL_SECONDS)
            status_changed.clear()

        if not running:
            break

        wait_until_order_deleted(key)


def handle_exit(signum: int, frame: Any) -> None:
    global running
    running = False
    status_changed.set()
    print(f"Received signal {signum}, exiting...")


def main() -> int:
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    streams = [
        db.child("boiler").child("status").stream(_status_handler_factory("boiler")),
        db.child("mixer").child("status").stream(_status_handler_factory("mixer")),
        db.child("garnish").child("status").stream(_status_handler_factory("garnish")),
    ]

    print("Kiosk worker started. Waiting for pending orders...")

    try:
        process_orders()
    finally:
        for stream in streams:
            stream.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
