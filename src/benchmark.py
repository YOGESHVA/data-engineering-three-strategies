import argparse, json, shutil, time
from pathlib import Path
from src.db import connect, seed_customers
from src.strategies import run_strategy, snapshot

def benchmark(source_file, db_path="data/benchmark.db"):
    if Path(db_path).exists(): Path(db_path).unlink()
    conn=connect(db_path)
    seed_customers(conn,[(i,f"Customer {i}") for i in range(1,101)])
    results=[]
    for strategy in ["full_refresh","incremental_merge","partition_replacement"]:
        result=run_strategy(conn,strategy,source_file)
        results.append(result)
    states={s:snapshot(conn,t) for s,t in [
        ("full_refresh","full_refresh_orders"),
        ("incremental_merge","incremental_orders"),
        ("partition_replacement","partition_orders")]}
    equivalent=states["full_refresh"]==states["incremental_merge"]==states["partition_replacement"]
    report={"results":results,"equivalent_results":equivalent,
            "row_count":len(states["full_refresh"])}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/strategy_comparison.json").write_text(json.dumps(report,indent=2))
    conn.close()
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="data/sample/orders_full.csv")
    p.add_argument("--db",default="data/benchmark.db")
    a=p.parse_args()
    benchmark(a.input,a.db)
