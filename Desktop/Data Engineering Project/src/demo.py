import csv
import tempfile
from pathlib import Path
from src.db import connect,seed_customers
from src.strategies import run_strategy,snapshot

def write_csv(path, rows):
    fields=["order_id","order_date","customer_id","amount","status","updated_at"]
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def run_demo():
    Path("data/sample").mkdir(parents=True,exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    temp_db = tempfile.NamedTemporaryFile(prefix="loading-demo-", suffix=".db", delete=False)
    temp_db.close()
    Path(temp_db.name).unlink(missing_ok=True)
    conn=connect(temp_db.name)
    seed_customers(conn,[(1,"Ravi"),(2,"Priya"),(3,"Arun")])
    base=[
      dict(order_id=101,order_date="2026-10-30",customer_id=1,amount=500,status="NEW",updated_at="2026-10-30T09:00:00Z"),
      dict(order_id=102,order_date="2026-10-30",customer_id=2,amount=800,status="PAID",updated_at="2026-10-30T09:05:00Z"),
      dict(order_id=103,order_date="2026-10-31",customer_id=3,amount=300,status="NEW",updated_at="2026-10-31T09:00:00Z"),
    ]
    changed=[
      dict(order_id=101,order_date="2026-10-30",customer_id=1,amount=500,status="NEW",updated_at="2026-10-30T09:00:00Z"),
      dict(order_id=102,order_date="2026-10-30",customer_id=2,amount=950,status="PAID",updated_at="2026-11-01T08:00:00Z"),
      dict(order_id=103,order_date="2026-10-31",customer_id=3,amount=300,status="NEW",updated_at="2026-10-31T09:00:00Z"),
      dict(order_id=104,order_date="2026-11-01",customer_id=1,amount=650,status="NEW",updated_at="2026-11-01T08:30:00Z"),
    ]
    p1="data/sample/orders_day1.csv"; p2="data/sample/orders_full.csv"
    write_csv(p1,base); write_csv(p2,changed)
    for s in ["full_refresh","incremental_merge","partition_replacement"]:
        run_strategy(conn,s,p1,changed_partitions=["2026-10-30","2026-10-31"])
    # Apply next complete snapshot to each strategy. For partition replacement,
    # only the changed date partitions are replaced, using complete partition rows.
    results={}
    for s in ["full_refresh","incremental_merge","partition_replacement"]:
        results[s]=run_strategy(conn,s,p2,changed_partitions=["2026-10-30","2026-11-01"])
    states=[snapshot(conn,t) for t in ["full_refresh_orders","incremental_orders","partition_orders"]]
    print("Second batch:",results)
    successful = all(r["status"] == "SUCCESS" for r in results.values())
    equivalent = successful and states[0] == states[1] == states[2]
    print("All strategies equivalent:", equivalent)
    print("Final records:",states[0])
    conn.close()
    Path(temp_db.name).unlink(missing_ok=True)

if __name__=="__main__": run_demo()
