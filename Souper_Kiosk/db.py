import sqlite3
import time
from typing import Any, Dict, Iterable, List, Tuple

DB_PATH = "souper_kiosk.db"

SOUP_ITEMS: List[str] = [
    "Chicken Broth",
    "Tomato Soup",
    "Beef Broth",
    "Vegetable Soup",
    "Mushroom Soup",
    "Miso Soup",
]

TOPPING_ITEMS: List[str] = [
    "Broccoli",
    "Carrots",
    "Chicken",
    "Tofu",
    "Croutons",
    "Cheese",
]


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firebase_key TEXT UNIQUE,
            soup_type TEXT NOT NULL,
            toppings TEXT,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp INTEGER NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            item_name TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity >= 0)
        )
        """
    )

    soup_rows = [(item, "soup", 10) for item in SOUP_ITEMS]
    topping_rows = [(item, "topping", 20) for item in TOPPING_ITEMS]
    conn.executemany(
        """
        INSERT OR IGNORE INTO inventory (item_name, category, quantity)
        VALUES (?, ?, ?)
        """,
        soup_rows + topping_rows,
    )
    conn.commit()


def get_inventory(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    cursor = conn.execute("SELECT item_name, category, quantity FROM inventory")
    rows = cursor.fetchall()
    return {
        row["item_name"]: {
            "category": row["category"],
            "quantity": int(row["quantity"]),
        }
        for row in rows
    }


def update_inventory(conn: sqlite3.Connection, changes: Dict[str, int], *, absolute: bool = False) -> None:
    if not changes:
        return

    with conn:
        for item_name, amount in changes.items():
            if absolute:
                conn.execute(
                    "UPDATE inventory SET quantity = MAX(0, ?) WHERE item_name = ?",
                    (int(amount), item_name),
                )
            else:
                conn.execute(
                    "UPDATE inventory SET quantity = MAX(0, quantity + ?) WHERE item_name = ?",
                    (int(amount), item_name),
                )


def insert_order(conn: sqlite3.Connection, order_data: Dict[str, Any]) -> None:
    toppings = order_data.get("toppings") or []
    if isinstance(toppings, (list, tuple)):
        toppings_text = ",".join(str(item) for item in toppings)
    else:
        toppings_text = str(toppings)

    timestamp = order_data.get("timestamp")
    if isinstance(timestamp, float):
        timestamp = int(timestamp)
    if not isinstance(timestamp, int):
        timestamp = int(time.time() * 1000)

    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO orders (
                firebase_key, soup_type, toppings, total, status, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                order_data.get("firebase_key"),
                order_data.get("soup_type", ""),
                toppings_text,
                float(order_data.get("total", 0.0)),
                order_data.get("status", "ready"),
                timestamp,
            ),
        )


def get_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    now = time.localtime()
    month_start = time.strptime(f"{now.tm_year}-{now.tm_mon:02d}-01", "%Y-%m-%d")
    month_start_ms = int(time.mktime(month_start) * 1000)

    revenue_row = conn.execute(
        """
        SELECT COALESCE(SUM(total), 0) AS month_revenue
        FROM orders
        WHERE timestamp >= ?
        """,
        (month_start_ms,),
    ).fetchone()

    soup_rows = conn.execute(
        """
        SELECT soup_type, COUNT(*) AS sold_count
        FROM orders
        WHERE timestamp >= ?
        GROUP BY soup_type
        ORDER BY sold_count DESC, soup_type ASC
        """,
        (month_start_ms,),
    ).fetchall()

    ranking: List[Tuple[str, int]] = [(row["soup_type"], int(row["sold_count"])) for row in soup_rows]

    return {
        "month_revenue": float(revenue_row["month_revenue"] if revenue_row else 0.0),
        "soup_ranking": ranking,
    }
