"""Manual stale-update demonstration. Safe to import; run as a script explicitly."""
from src.db import connect
from src.strategies import run_strategy


def main():
    conn = connect("data/large.db")
    try:
        before = conn.execute("SELECT order_id,amount,status,updated_at FROM incremental_orders WHERE order_id=100003").fetchone()
        print("BEFORE:", dict(before) if before else "row not present")
        print("RESULT:", run_strategy(conn, "incremental_merge", "data/batch2/out_of_order.csv"))
        after = conn.execute("SELECT order_id,amount,status,updated_at FROM incremental_orders WHERE order_id=100003").fetchone()
        print("AFTER:", dict(after) if after else "row not present")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
