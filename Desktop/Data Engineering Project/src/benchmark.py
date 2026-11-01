"""Safe, repeatable benchmark for the three loading strategies."""
import argparse, json, statistics, sys, tempfile, time
from decimal import Decimal
from pathlib import Path
from src.db import connect, seed_customers
from src.strategies import run_strategy, snapshot

def _cents(value):
    try:
        amount=Decimal(str(value))
        return int(amount*100) if amount.is_finite() else 0
    except Exception:
        return 0

STRATEGIES = [("full_refresh", "full_refresh_orders"), ("incremental_merge", "incremental_orders"), ("partition_replacement", "partition_orders")]

def benchmark(source_file, db_path=None, report_path="reports/strategy_comparison.json", reset=False, trials=3):
    source = Path(source_file)
    if not source.is_file(): raise FileNotFoundError(f"Input CSV does not exist: {source}")
    if trials < 1: raise ValueError("trials must be at least 1")
    if db_path:
        db = Path(db_path)
        if db.exists() and not reset: raise FileExistsError(f"Refusing to overwrite existing database: {db}; use --reset explicitly")
        if db.exists(): db.unlink()
        db.parent.mkdir(parents=True, exist_ok=True)
        dbs = [db]
    else:
        dbs = []
    trial_reports=[]
    for trial in range(trials):
        if db_path:
            trial_db = dbs[0] if trial == 0 else dbs[0].with_name(f"{dbs[0].stem}_trial{trial+1}{dbs[0].suffix}")
            if trial_db.exists():
                if not reset: raise FileExistsError(f'Refusing to overwrite trial database: {trial_db}; pass --reset explicitly')
                trial_db.unlink()
        else:
            tmp = tempfile.NamedTemporaryFile(prefix="strategy_benchmark_", suffix=".db", delete=False); trial_db=Path(tmp.name); tmp.close()
        conn=connect(trial_db)
        seed_customers(conn, [(i, f"Customer {i}") for i in range(1,1001)])
        # Each strategy starts with an independent empty target in the same isolated DB.
        results={}; states={}; timings={}
        # Rotate order to reduce systematic order bias.
        ordered=STRATEGIES[trial % len(STRATEGIES):]+STRATEGIES[:trial % len(STRATEGIES)]
        for strategy, table in ordered:
            t=time.perf_counter(); result=run_strategy(conn,strategy,str(source)); timings[strategy]=(time.perf_counter()-t)*1000
            results[strategy]=result; states[strategy]=snapshot(conn,table)
        execution_success=all(r["status"]=="SUCCESS" and r.get("rejected_count",0)==0 for r in results.values())
        # Independent expected oracle: parse source rows, retain first valid unique key;
        # source validator/reject counts are reported separately. Oracle is deliberately
        # constructed from the CSV rather than calling any loading strategy.
        import csv
        expected=[]
        with source.open(newline="",encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    expected.append((int(row['order_id']),row['order_date'],int(row['customer_id']),float(row['amount']),row['status'],row['updated_at']))
                except (ValueError,KeyError,TypeError): pass
        by_id={}
        for row in expected: by_id.setdefault(row[0],row)
        expected_rows=sorted(by_id.values(),key=lambda x:x[0])
        # timestamps are canonicalized by pipeline; normalize oracle timestamp too.
        from src.strategies import normalize_timestamp
        expected_rows=[r[:5]+(normalize_timestamp(r[5]),) for r in expected_rows]
        oracle_match={s:(states.get(s)==expected_rows) for s,_ in STRATEGIES} if execution_success else {}
        equivalent=all(states[s]==states[STRATEGIES[0][0]] for s,_ in STRATEGIES) if execution_success else None
        expected_keys={r[0] for r in expected_rows}
        expected_cents=sum(_cents(r[3]) for r in expected_rows)
        oracle_checks={s:{"row_count":len(states[s]),"key_set_match":{r[0] for r in states[s]}==expected_keys,
                          "amount_total_cents":sum(_cents(r[3]) for r in states[s]),
                          "amount_total_cents_match":sum(_cents(r[3]) for r in states[s])==expected_cents}
                       for s,_ in STRATEGIES} if execution_success else {}
        passed=bool(execution_success and equivalent and all(oracle_match.values()) and all(v['key_set_match'] and v['amount_total_cents_match'] for v in oracle_checks.values()))
        trial_reports.append({"trial":trial+1,"execution_success":execution_success,"data_equivalent":equivalent,"oracle_match":oracle_match,"oracle_checks":oracle_checks,"expected_amount_total_cents":expected_cents,"comparison_passed":passed,"results":results,"timings_ms":timings,"row_count":len(expected_rows)})
        conn.close()
        if not db_path: trial_db.unlink(missing_ok=True)
    medians={s:round(statistics.median(t["timings_ms"][s] for t in trial_reports),3) for s,_ in STRATEGIES}
    report={"trials":trials,"timing_statistic":"median","median_duration_ms":medians,"comparison_passed":all(t['comparison_passed'] for t in trial_reports),"trial_results":trial_reports,"workload":"single supplied CSV; initial load; SQLite local benchmark","limitations":"This benchmark measures the supplied initial-load workload. Use a separately prepared base/delta/complete-partition scenario to compare later-batch workloads."}
    out=Path(report_path); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2)); return report

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--input',default='data/sample/orders_full.csv'); p.add_argument('--db'); p.add_argument('--report',default='reports/strategy_comparison.json'); p.add_argument('--reset',action='store_true'); p.add_argument('--trials',type=int,default=3); a=p.parse_args()
    try: sys.exit(0 if benchmark(a.input,a.db,a.report,a.reset,a.trials)['comparison_passed'] else 1)
    except Exception as e: print(f'Benchmark failed: {e}',file=sys.stderr); sys.exit(1)
