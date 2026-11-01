
from src.db import connect
from src.strategies import run_strategy, snapshot

DB = "data/large.db"

conn = connect(DB)

try:
    results = []

    print("\n1. Running FULL REFRESH...")
    results.append(
        run_strategy(
            conn,
            "full_refresh",
            "data/batch2/full_refresh_batch2.csv"
        )
    )

    print("\n2. Running INCREMENTAL MERGE...")
    results.append(
        run_strategy(
            conn,
            "incremental_merge",
            "data/batch2/incremental_batch2.csv"
        )
    )

    print("\n3. Running PARTITION REPLACEMENT...")
    results.append(
        run_strategy(
            conn,
            "partition_replacement",
            "data/batch2/partition_batch2.csv",
            changed_partitions=["2026-01-21", "2026-11-01"]
        )
    )

    print("\n========== RESULTS ==========")

    for result in results:
        print(result)

    full = snapshot(conn, "full_refresh_orders")
    incremental = snapshot(conn, "incremental_orders")
    partition = snapshot(conn, "partition_orders")

    equivalent = full == incremental == partition

    print("\n========== RECONCILIATION ==========")
    print("Full refresh rows:", len(full))
    print("Incremental rows:", len(incremental))
    print("Partition rows:", len(partition))
    print("Equivalent results:", equivalent)

finally:
    conn.close()
