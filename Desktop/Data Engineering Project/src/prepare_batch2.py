import csv
import sqlite3
from pathlib import Path


def main():
    DB = "data/large.db"
    BATCH = "data/batch2/orders_batch2.csv"
    OUTPUT = Path("data/batch2")

    COLUMNS = [
        "order_id", "order_date", "customer_id",
        "amount", "status", "updated_at"
    ]

    # Read the second batch
    with open(BATCH, newline="", encoding="utf-8") as f:
        batch = list(csv.DictReader(f))

    # Read the existing baseline
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    baseline = [
        dict(row) for row in conn.execute(
            "SELECT order_id, order_date, customer_id, "
            "amount, status, updated_at FROM incremental_orders"
        )
    ]
    conn.close()

    # Build the complete updated snapshot for full refresh
    full_data = {int(row["order_id"]): row for row in baseline}

    for row in batch:
        full_data[int(row["order_id"])] = row

    full_rows = list(full_data.values())

    # Build complete contents of affected partitions
    changed_dates = {"2026-01-21", "2026-11-01"}

    partition_data = {
        int(row["order_id"]): row
        for row in baseline
        if row["order_date"] in changed_dates
    }

    for row in batch:
        partition_data[int(row["order_id"])] = row

    partition_rows = list(partition_data.values())

    def write_csv(filename, rows):
        path = OUTPUT / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Created {path}: {len(rows)} records")

    write_csv("full_refresh_batch2.csv", full_rows)
    write_csv("incremental_batch2.csv", batch)
    write_csv("partition_batch2.csv", partition_rows)

    print("\nInput preparation completed.")
    print("Affected partitions:", sorted(changed_dates))


if __name__ == "__main__":
    main()
