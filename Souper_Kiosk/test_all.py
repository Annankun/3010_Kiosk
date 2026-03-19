import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# sys.modules stubs — must happen before any project imports
# ---------------------------------------------------------------------------

def _make_pyrebase_stub():
    mod = types.ModuleType("pyrebase")
    mock_db = MagicMock()
    mock_app = MagicMock()
    mock_app.database.return_value = mock_db
    mod.initialize_app = MagicMock(return_value=mock_app)
    return mod, mock_db

_pyrebase_stub, _pyrebase_db = _make_pyrebase_stub()
sys.modules.setdefault("pyrebase", _pyrebase_stub)

_gpio = types.ModuleType("RPi")
_gpio_gpio = types.ModuleType("RPi.GPIO")
_gpio_gpio.BCM = 11
_gpio_gpio.OUT = 0
_gpio_gpio.HIGH = 1
_gpio_gpio.LOW = 0
_gpio_gpio.setmode = MagicMock()
_gpio_gpio.setup = MagicMock()
_gpio_gpio.output = MagicMock()
_gpio_gpio.cleanup = MagicMock()
_gpio.GPIO = _gpio_gpio
sys.modules.setdefault("RPi", _gpio)
sys.modules.setdefault("RPi.GPIO", _gpio_gpio)

_picamera2_mod = types.ModuleType("picamera2")
_picamera2_mod.Picamera2 = MagicMock()
sys.modules.setdefault("picamera2", _picamera2_mod)

_cv2 = types.ModuleType("cv2")
_cv2.imshow = MagicMock()
_cv2.waitKey = MagicMock(return_value=0)
_cv2.destroyAllWindows = MagicMock()
sys.modules.setdefault("cv2", _cv2)

_pyzbar = types.ModuleType("pyzbar")
_pyzbar_pyzbar = types.ModuleType("pyzbar.pyzbar")
_pyzbar_pyzbar.decode = MagicMock(return_value=[])
_pyzbar.pyzbar = _pyzbar_pyzbar
sys.modules.setdefault("pyzbar", _pyzbar)
sys.modules.setdefault("pyzbar.pyzbar", _pyzbar_pyzbar)

_config = types.ModuleType("config")
_config.FIREBASE_CONFIG = {}
sys.modules.setdefault("config", _config)

# ---------------------------------------------------------------------------
# Project imports (after stubs are in place)
# ---------------------------------------------------------------------------

import sqlite3

import db as sqlite_tools

# kiosk and scanner patch sqlite_conn / db at module level; import them now
# so the stubs above take effect at import time.
import kiosk
import scanner

# ---------------------------------------------------------------------------
# db.py tests
# ---------------------------------------------------------------------------

class TestDbInit(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        sqlite_tools.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_soup_default_quantity(self):
        inv = sqlite_tools.get_inventory(self.conn)
        self.assertEqual(inv["Chicken Broth"]["quantity"], 10)

    def test_topping_default_quantity(self):
        inv = sqlite_tools.get_inventory(self.conn)
        self.assertEqual(inv["Broccoli"]["quantity"], 20)

    def test_decrement_inventory(self):
        sqlite_tools.update_inventory(self.conn, {"Chicken Broth": -1})
        inv = sqlite_tools.get_inventory(self.conn)
        self.assertEqual(inv["Chicken Broth"]["quantity"], 9)

    def test_inventory_cannot_go_negative(self):
        sqlite_tools.update_inventory(self.conn, {"Chicken Broth": -999})
        inv = sqlite_tools.get_inventory(self.conn)
        self.assertEqual(inv["Chicken Broth"]["quantity"], 0)

    def test_insert_order(self):
        sqlite_tools.insert_order(self.conn, {
            "firebase_key": "key1",
            "soup_type": "Tomato Soup",
            "toppings": ["Carrots"],
            "total": 8.5,
            "status": "ready",
            "timestamp": 1700000000000,
        })
        row = self.conn.execute("SELECT * FROM orders WHERE firebase_key = 'key1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["soup_type"], "Tomato Soup")

    def test_monthly_stats(self):
        import time
        now_ms = int(time.time() * 1000)
        sqlite_tools.insert_order(self.conn, {
            "firebase_key": "key2",
            "soup_type": "Miso Soup",
            "toppings": [],
            "total": 5.0,
            "status": "ready",
            "timestamp": now_ms,
        })
        stats = sqlite_tools.get_stats(self.conn)
        self.assertGreaterEqual(stats["month_revenue"], 5.0)
        self.assertEqual(stats["soup_ranking"][0][0], "Miso Soup")

# ---------------------------------------------------------------------------
# kiosk.py tests
# ---------------------------------------------------------------------------

class TestKiosk(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        sqlite_tools.init_db(self.conn)
        self._orig_conn = kiosk.sqlite_conn
        kiosk.sqlite_conn = self.conn

    def tearDown(self):
        kiosk.sqlite_conn = self._orig_conn
        self.conn.close()

    def test_can_fulfill_order_sufficient(self):
        result = kiosk.can_fulfill_order({
            "soup_type": "Chicken Broth",
            "toppings": ["Broccoli"],
        })
        self.assertTrue(result)

    def test_can_fulfill_order_empty_inventory(self):
        sqlite_tools.update_inventory(self.conn, {"Chicken Broth": -10})
        result = kiosk.can_fulfill_order({
            "soup_type": "Chicken Broth",
            "toppings": [],
        })
        self.assertFalse(result)

    def test_all_components_complete_all_done(self):
        with kiosk.status_lock:
            kiosk.component_status["boiler"] = "complete"
            kiosk.component_status["mixer"] = "complete"
            kiosk.component_status["garnish"] = "complete"
        self.assertTrue(kiosk.all_components_complete())

    def test_all_components_complete_one_missing(self):
        with kiosk.status_lock:
            kiosk.component_status["boiler"] = "complete"
            kiosk.component_status["mixer"] = "complete"
            kiosk.component_status["garnish"] = ""
        self.assertFalse(kiosk.all_components_complete())

# ---------------------------------------------------------------------------
# scanner.py tests
# ---------------------------------------------------------------------------

class TestScannerSkip(unittest.TestCase):
    def setUp(self):
        scanner.last_scanned_key = ""
        scanner.last_scan_time = 0.0

    def tearDown(self):
        scanner.last_scanned_key = ""
        scanner.last_scan_time = 0.0

    def test_first_scan_allowed(self):
        self.assertFalse(scanner.should_skip_scan("order123"))

    def test_duplicate_within_cooldown_blocked(self):
        scanner.should_skip_scan("order123")
        self.assertTrue(scanner.should_skip_scan("order123"))

    def test_different_key_allowed(self):
        scanner.should_skip_scan("order123")
        self.assertFalse(scanner.should_skip_scan("order456"))


class TestScannerHandle(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self._orig_db = scanner.db
        scanner.db = self.mock_db
        _gpio_gpio.output.reset_mock()

    def tearDown(self):
        scanner.db = self._orig_db

    def test_ready_order_triggers_green_led(self):
        self.mock_db.child.return_value.child.return_value.get.return_value.val.return_value = {
            "status": "ready"
        }
        with patch("scanner.time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.time = __import__("time").time
            scanner.flash_led = MagicMock()
            scanner.handle_scan("order123")
        self.mock_db.child.return_value.child.return_value.remove.assert_called_once()

    def test_missing_order_triggers_red_led(self):
        self.mock_db.child.return_value.child.return_value.get.return_value.val.return_value = None
        with patch("scanner.flash_led") as mock_flash:
            scanner.handle_scan("order_missing")
        mock_flash.assert_called_once_with(scanner.RED_LED_PIN)


if __name__ == "__main__":
    unittest.main()
