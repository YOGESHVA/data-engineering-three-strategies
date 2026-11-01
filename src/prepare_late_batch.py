
import csv
import sqlite3
from pathlib import Path

DB = "data/large.db"
LATE_FILE = "data/batch2/late_orders.csv"
OUTPUT = Path("data/batch2")

COLUMNS = [
    "order_id", "order_date", "customer_id",
    "amount", "status", "updated_at"
]

# Read the late-arriving record
with open(LATE_FILE, newline="", encoding="utf-8") as f:
    late_rows = list(csv.DictReader(f))

if len(late_rows) != 1:
    raise ValueError("Expected exactly one late-arriving record")

# Read the current baseline
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

baseline = [
    dict(row) for row in conn.execute(
        "SELECT order_id, order_date, customer_id, "
        "amount, status, updated_at FROM incremental_orders"
    )
]
conn.close()

# Full refresh: complete dataset plus late record
full_data = {int(r["order_id"]): r for r in baseline}

for row in late_rows:
    full_data[int(row["order_id"])] = row

# Partition replacement: complete October 30 partition
partition_data = {
    int(r["order_id"]): r
    for r in baseline
    if r["order_date"] == "2026-10-30"
}

for row in late_rows:
    partition_data[int(row["order_id"])] = row

def write_csv(filename, rows):
    path = OUTPUT / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {filename}: {len(rows)} records")

write_csv("full_refresh_late.csv", list(full_data.values()))
write_csv("incremental_late.csv", late_rows)
write_csv("partition_late.csv", list(partition_data.values()))

print("\nLate-arriving data preparation completed.")
print("Affected partition: 2026-10-30")
