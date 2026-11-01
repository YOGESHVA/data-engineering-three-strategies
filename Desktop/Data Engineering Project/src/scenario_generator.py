"""Create deterministic base/delta/partition inputs and an independent expected state."""
import csv, json, random
from datetime import date, timedelta
from pathlib import Path
FIELDS=['order_id','order_date','customer_id','amount','status','updated_at']
STATUSES=['NEW','PAID','SHIPPED','DELIVERED']
def _write(path, rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
def generate_scenario(output_dir, base_rows=1000, updates=50, inserts=50, seed=42):
    if min(base_rows,updates,inserts)<0: raise ValueError('scenario counts cannot be negative')
    rng=random.Random(seed); start=date(2026,1,1); base=[]
    for i in range(1,base_rows+1):
        d=start+timedelta(days=(i-1)%10)
        base.append(dict(order_id=i,order_date=d.isoformat(),customer_id=rng.randint(1,100),amount=f'{rng.randint(100,500000)/100:.2f}',status=rng.choice(STATUSES),updated_at=f'{d.isoformat()}T10:00:00Z'))
    final={r['order_id']:dict(r) for r in base}; delta=[]
    # Keep the change workload concentrated in two dates so partition replacement
    # processes a realistic affected subset rather than the entire ten-day base.
    affected_candidate_dates={(start+timedelta(days=i)).isoformat() for i in (0,1)}
    update_candidates=[r for r in base if r['order_date'] in affected_candidate_dates]
    for original in update_candidates[:updates]:
        oid=int(original['order_id']);r=dict(final[oid]);r['amount']=f'{float(r["amount"])+1.25:.2f}';r['status']='PAID';r['updated_at']='2026-02-01T12:00:00Z';final[oid]=r;delta.append(r)
    insert_date=(start+timedelta(days=0)).isoformat()
    for oid in range(base_rows+1,base_rows+inserts+1):
        r=dict(order_id=oid,order_date=insert_date,customer_id=rng.randint(1,100),amount=f'{rng.randint(100,500000)/100:.2f}',status='NEW',updated_at='2026-02-01T12:00:00Z')
        final[oid]=r;delta.append(r)
    affected=sorted({r['order_date'] for r in delta})
    partition=[r for r in final.values() if r['order_date'] in affected]
    out=Path(output_dir);_write(out/'base.csv',base);_write(out/'full_refresh_final.csv',list(final.values()));_write(out/'incremental_delta.csv',delta);_write(out/'partition_complete_affected.csv',partition);_write(out/'expected_final.csv',list(final.values()))
    manifest={'seed':seed,'base_records':len(base),'update_records':min(updates,len(update_candidates)),'insert_records':inserts,'delta_records':len(delta),'affected_partitions':affected,'partition_snapshot_records':len(partition),'expected_final_records':len(final),'contract':'incremental input is updates+inserts; partition input is a complete snapshot of every affected date'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');return manifest
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='data/scenario');p.add_argument('--base-rows',type=int,default=1000);p.add_argument('--updates',type=int,default=50);p.add_argument('--inserts',type=int,default=50);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    print(json.dumps(generate_scenario(a.output,a.base_rows,a.updates,a.inserts,a.seed),indent=2))

def generate_adversarial_feed(base_csv, output_dir, seed=42):
    """Write a deterministic labelled QA feed; labels stay separate from pipeline columns."""
    rng=random.Random(seed); base=_read_rows(base_csv)
    if len(base)<2: raise ValueError('base_csv must contain at least two rows')
    first=dict(base[0]); second=dict(base[1])
    update=dict(first);update['amount']=f'{float(update["amount"])+2.00:.2f}';update['updated_at']='2026-03-01T12:00:00Z';update['status']='PAID'
    exact_duplicate=dict(update)
    conflict=dict(update);conflict['amount']=f'{float(update["amount"])+1:.2f}'
    stale=dict(second);stale['amount']='1.00';stale['updated_at']='2020-01-01T00:00:00Z'
    late={'order_id':900003,'order_date':'2025-12-01','customer_id':rng.randint(1,100),'amount':'12.50','status':'NEW','updated_at':'2026-03-01T12:00:00Z'}
    missing={'order_id':900001,'order_date':'2026-01-01','customer_id':1,'amount':'','status':'NEW','updated_at':'2026-03-01T12:00:00Z'}
    bad_fk={'order_id':900002,'order_date':'2026-01-01','customer_id':999999,'amount':'9.00','status':'NEW','updated_at':'2026-03-01T12:00:00Z'}
    records=[update,exact_duplicate,conflict,stale,late,missing,bad_fk]
    out=Path(output_dir);_write(out/'adversarial_feed.csv',records)
    labels={'seed':seed,'records':[{'source_record_number':1,'expected':'update_existing'},{'source_record_number':2,'expected':'exact_duplicate'},{'source_record_number':3,'expected':'conflicting_duplicate_reject'},{'source_record_number':4,'expected':'stale_out_of_order_update'},{'source_record_number':5,'expected':'late_arrival_insert'},{'source_record_number':6,'expected':'missing_amount_reject'},{'source_record_number':7,'expected':'unknown_customer_reject'}]}
    (out/'adversarial_labels.json').write_text(json.dumps(labels,indent=2),encoding='utf-8');return labels

def _read_rows(path):
    with open(path,newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
