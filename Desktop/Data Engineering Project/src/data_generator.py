import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

FIELDS = ["order_id", "order_date", "customer_id", "amount", "status", "updated_at"]


def generate(path, rows=10000, seed=42):
    if rows < 0:
        raise ValueError("rows must be zero or greater")
    rng = random.Random(seed)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for i in range(1, rows + 1):
            day = start + timedelta(days=rng.randrange(30))
            writer.writerow({
                "order_id": i,
                "order_date": day.isoformat(),
                "customer_id": rng.randint(1, 100),
                "amount": f"{rng.uniform(1, 5000):.2f}",
                "status": rng.choice(["NEW", "PAID", "SHIPPED", "CANCELLED"]),
                "updated_at": f"{day.isoformat()}T12:{i % 60:02d}:00Z",
            })
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/generated/orders.csv")
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(f"Generated {generate(args.output, args.rows, args.seed)} rows at {args.output}")
