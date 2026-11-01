from src.db import connect
from src.strategies import run_strategy

conn = connect("data/large.db")

try:
    print("BEFORE STALE UPDATE")

    before = conn.execute("""
        SELECT order_id, amount, status, updated_at
        FROM incremental_orders
        WHERE order_id = 100003
    """).fetchone()

    print(dict(before))

    print("\nPROCESSING OLDER UPDATE")

    result = run_strategy(
        conn,
        "incremental_merge",
        "data/batch2/out_of_order.csv"
    )

    print(result)

    print("\nAFTER STALE UPDATE")

    after = conn.execute("""
        SELECT order_id, amount, status, updated_at
        FROM incremental_orders
        WHERE order_id = 100003
    """).fetchone()

    print(dict(after))

finally:
    conn.close()