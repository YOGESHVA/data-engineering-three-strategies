import argparse, csv, random
from datetime import date, timedelta
from pathlib import Path

FIELDS = ["order_id","order_date","customer_id","amount","status","updated_at"]

def generate(path, rows=10000, seed=42):
    random.seed(seed)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for i in range(1, rows + 1):
            day = start + timedelta(days=random.randrange(30))
            writer.writerow({
                "order_id": i,
                "order_date": day.isoformat(),
                "customer_id": random.randint(1,100),
                "amount": round(random.uniform(1,5000),2),
                "status": random.choice(["NEW","PAID","SHIPPED","CANCELLED"]),
                "updated_at": f"{day.isoformat()}T12:{i%60:02d}:00"
            })
    return rows

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="data/generated/orders.csv")
    p.add_argument("--rows",type=int,default=100000)
    p.add_argument("--seed",type=int,default=42)
    a=p.parse_args()
    print(f"Generated {generate(a.output,a.rows,a.seed)} rows at {a.output}")
