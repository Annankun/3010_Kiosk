import time

import db as sqlite_tools


def main() -> int:
    conn = sqlite_tools.connect()
    try:
        sqlite_tools.init_db(conn)
        stats = sqlite_tools.get_stats(conn)
    finally:
        conn.close()

    month_label = time.strftime("%Y-%m")
    print(f"=== Souper Kiosk Stats ({month_label}) ===")
    print(f"Monthly revenue: ${stats['month_revenue']:.2f}")

    ranking = stats.get("soup_ranking", [])
    print("Soup sales ranking:")
    if not ranking:
        print("  (no soup sales this month)")
        return 0

    for idx, (soup_name, sold_count) in enumerate(ranking, start=1):
        print(f"  {idx}. {soup_name} - {sold_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
