
from src.db import connect
from src.strategies import run_strategy, snapshot

conn = connect("data/large.db")

try:
    results = []

    print("\n1. FULL REFRESH")
    results.append(
        run_strategy(
            conn,
            "full_refresh",
            "data/batch2/full_refresh_late.csv"
        )
    )

    print("\n2. INCREMENTAL MERGE")
    results.append(
        run_strategy(
            conn,
            "incremental_merge",
            "data/batch2/incremental_late.csv"
        )
    )

    print("\n3. PARTITION REPLACEMENT")
    results.append(
        run_strategy(
            conn,
            "partition_replacement",
            "data/batch2/partition_late.csv",
            changed_partitions=["2026-10-30"]
        )
    )

    print("\n========== RESULTS ==========")
    for result in results:
        print(result)

    full = snapshot(conn, "full_refresh_orders")
    incremental = snapshot(conn, "incremental_orders")
    partition = snapshot(conn, "partition_orders")

    print("\n========== RECONCILIATION ==========")
    print("Full refresh:", len(full))
    print("Incremental merge:", len(incremental))
    print("Partition replacement:", len(partition))
    print("Equivalent results:", full == incremental == partition)

    print("\n========== LATE ORDER CHECK ==========")

    for table in [
        "full_refresh_orders",
        "incremental_orders",
        "partition_orders"
    ]:
        row = conn.execute(
            f"""
            SELECT order_id, order_date, amount, status
            FROM {table}
            WHERE order_id = 100003
            """
        ).fetchone()

        print(table, dict(row) if row else None)

finally:
    conn.close()
