"""Regression coverage for reviewer acceptance criteria C01-C13."""
import csv, json, sqlite3
from pathlib import Path
import pytest
from src.db import connect, seed_customers
from src.strategies import run_strategy, snapshot
from src.benchmark import benchmark

FIELDS=['order_id','order_date','customer_id','amount','status','updated_at']
def row(i=1,date='2026-01-01',amount='10.00',ts='2026-01-01T10:00:00Z',status='NEW',cid=1):
    return dict(order_id=i,order_date=date,customer_id=cid,amount=amount,status=status,updated_at=ts)
def write(path, rows):
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    return str(path)
def setup(tmp):
    c=connect(tmp/'x.db');seed_customers(c,[(1,'A'),(2,'B')]);return c

def test_timezone_offsets_compare_by_instant(tmp_path):
    c=setup(tmp_path);run_strategy(c,'incremental_merge',write(tmp_path/'a.csv',[row(amount='100',ts='2026-01-01T10:00:00Z')]))
    r=run_strategy(c,'incremental_merge',write(tmp_path/'b.csv',[row(amount='999',ts='2026-01-01T11:00:00+02:00')]))
    assert r['stale_count']==1 and snapshot(c,'incremental_orders')[0][3]==100

def test_equivalent_timestamp_same_payload_is_noop(tmp_path):
    c=setup(tmp_path);run_strategy(c,'incremental_merge',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'incremental_merge',write(tmp_path/'b.csv',[row(ts='2026-01-01T15:30:00+05:30')]))
    assert r['unchanged_count']==1

def test_equal_timestamp_conflicting_payload_fails(tmp_path):
    c=setup(tmp_path);run_strategy(c,'incremental_merge',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'incremental_merge',write(tmp_path/'b.csv',[row(amount='11')]))
    assert r['status']=='FAILED'

def test_naive_timestamp_rejected(tmp_path):
    c=setup(tmp_path);r=run_strategy(c,'full_refresh',write(tmp_path/'a.csv',[row(ts='2026-01-01T10:00:00')]))
    assert r['rejected_count']==1

def test_fractional_timestamp_normalized(tmp_path):
    c=setup(tmp_path);r=run_strategy(c,'full_refresh',write(tmp_path/'a.csv',[row(ts='2026-01-01T10:00:00.1Z')]))
    assert r['status']=='SUCCESS' and snapshot(c,'full_refresh_orders')[0][5].endswith('.100000Z')

def test_physical_source_count_and_exact_duplicates(tmp_path):
    c=setup(tmp_path);r=run_strategy(c,'full_refresh',write(tmp_path/'a.csv',[row(),row()]))
    assert (r['source_records'],r['accepted_count'],r['duplicate_count'],r['rejected_count'])==(2,1,1,0)

def test_extra_and_short_fields_rejected(tmp_path):
    c=setup(tmp_path);p=tmp_path/'extra.csv';p.write_text(','.join(FIELDS)+'\n1,2026-01-01,1,10,NEW,2026-01-01T10:00:00Z,EXTRA\n')
    r=run_strategy(c,'full_refresh',str(p));assert r['rejected_count']==1

def test_duplicate_headers_fail_clearly(tmp_path):
    c=setup(tmp_path);p=tmp_path/'dup.csv';p.write_text('order_id,order_id,customer_id,amount,status,updated_at\n1,1,1,10,NEW,2026-01-01T10:00:00Z\n')
    r=run_strategy(c,'full_refresh',str(p));assert r['status']=='FAILED'

def test_nonfinite_values_rejected(tmp_path):
    c=setup(tmp_path);r=run_strategy(c,'full_refresh',write(tmp_path/'a.csv',[row(amount='NaN'),row(2,amount='Infinity')]))
    assert r['rejected_count']==2 and snapshot(c,'full_refresh_orders')==[]

def test_malformed_quoted_csv_fails(tmp_path):
    c=setup(tmp_path);p=tmp_path/'bad.csv';p.write_text(','.join(FIELDS)+'\n1,2026-01-01,1,10,NEW,"unterminated\n')
    r=run_strategy(c,'full_refresh',str(p));assert r['status']=='FAILED'

def test_partition_empty_scope_is_noop(tmp_path):
    c=setup(tmp_path);run_strategy(c,'partition_replacement',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'partition_replacement',write(tmp_path/'b.csv',[row(2,'2026-01-02')]),changed_partitions=[])
    assert r['status']=='SUCCESS' and r['ignored_scope_count']==1 and len(snapshot(c,'partition_orders'))==1

def test_partition_move_requires_both_partitions(tmp_path):
    c=setup(tmp_path);run_strategy(c,'partition_replacement',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'partition_replacement',write(tmp_path/'b.csv',[row(date='2026-01-02',ts='2026-01-02T10:00:00Z')]),changed_partitions=['2026-01-02'])
    assert r['status']=='FAILED'

def test_partition_move_with_both_partitions_succeeds(tmp_path):
    c=setup(tmp_path);run_strategy(c,'partition_replacement',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'partition_replacement',write(tmp_path/'b.csv',[row(date='2026-01-02',ts='2026-01-02T10:00:00Z')]),changed_partitions=['2026-01-01','2026-01-02'])
    assert r['status']=='SUCCESS' and snapshot(c,'partition_orders')[0][1]=='2026-01-02'

def test_rejects_survive_failed_target_transaction(tmp_path):
    c=setup(tmp_path);r=run_strategy(c,'full_refresh',write(tmp_path/'a.csv',[row(),row(2,amount='-1')]),fail_before_commit=True)
    assert r['status']=='FAILED' and c.execute('select count(*) from rejects').fetchone()[0]==1
    assert snapshot(c,'full_refresh_orders')==[]

def test_failure_rolls_back_populated_target(tmp_path):
    c=setup(tmp_path);run_strategy(c,'incremental_merge',write(tmp_path/'a.csv',[row()]))
    r=run_strategy(c,'incremental_merge',write(tmp_path/'b.csv',[row(2,'2026-01-02')]),fail_before_commit=True)
    assert r['status']=='FAILED' and len(snapshot(c,'incremental_orders'))==1

def test_all_strategies_are_rerunnable(tmp_path):
    c=setup(tmp_path);p=write(tmp_path/'a.csv',[row()])
    for strategy in ['full_refresh','incremental_merge','partition_replacement']:
        assert run_strategy(c,strategy,p)['status']=='SUCCESS'
        assert run_strategy(c,strategy,p)['status']=='SUCCESS'

def test_target_foreign_keys_enforced(tmp_path):
    c=setup(tmp_path)
    for table in ['full_refresh_orders','incremental_orders','partition_orders']:
        with pytest.raises(sqlite3.IntegrityError):c.execute(f"insert into {table} values (1,'2026-01-01',999,1,'NEW','2026-01-01T00:00:00Z')")
        c.rollback()

def test_run_source_hash_and_lineage_recorded(tmp_path):
    c=setup(tmp_path);p=write(tmp_path/'a.csv',[row()]);r=run_strategy(c,'incremental_merge',p)
    run=c.execute('select source_file,source_sha256,input_mode from pipeline_runs where run_id=?',(r['run_id'],)).fetchone()
    assert run[0] and len(run[1])==64 and run[2]=='change_feed'
    log=c.execute('select count(*) from change_log where run_id=?',(r['run_id'],)).fetchone()[0]
    assert log==1

def test_benchmark_success_requires_oracle_and_repeated_trials(tmp_path):
    p=write(tmp_path/'input.csv',[row()]);report=benchmark(p,report_path=tmp_path/'report.json',trials=2)
    assert report['comparison_passed'] and report['trials']==2
    assert all(all(t['oracle_match'].values()) for t in report['trial_results'])

def test_benchmark_refuses_existing_db(tmp_path):
    p=write(tmp_path/'input.csv',[row()]);db=tmp_path/'existing.db';db.write_bytes(b'keep')
    with pytest.raises(FileExistsError):benchmark(p,db_path=db,report_path=tmp_path/'r.json')
    assert db.read_bytes()==b'keep'

def test_negative_generator_count_rejected(tmp_path):
    from src.data_generator import generate
    with pytest.raises(ValueError):generate(tmp_path/'x.csv',-1)

def test_later_batch_scenario_matches_independent_expected_state(tmp_path):
    from src.later_batch_benchmark import run
    report=run(str(tmp_path/'scenario'),base_rows=100,updates=10,inserts=5,seed=7,trials=2,report=str(tmp_path/'later.json'))
    assert report['comparison_passed'] is True
    assert report['manifest']['delta_records']==15

def test_reject_lineage_contains_physical_record_number(tmp_path):
    c=setup(tmp_path);p=write(tmp_path/'reject.csv',[row(),row(2,amount='-5')])
    r=run_strategy(c,'full_refresh',p)
    rec=c.execute('select source_record_number from rejects where run_id=?',(r['run_id'],)).fetchone()
    assert rec[0]==2

def test_empty_complete_partition_removes_existing_partition(tmp_path):
    c=setup(tmp_path);run_strategy(c,'partition_replacement',write(tmp_path/'base.csv',[row()]))
    empty=tmp_path/'empty.csv';write(empty,[])
    r=run_strategy(c,'partition_replacement',str(empty),changed_partitions=['2026-01-01'])
    assert r['status']=='SUCCESS' and snapshot(c,'partition_orders')==[]

def test_foreign_key_check_is_clean(tmp_path):
    c=setup(tmp_path);run_strategy(c,'full_refresh',write(tmp_path/'base.csv',[row()]))
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

def test_adversarial_generator_separates_labels_from_pipeline_data(tmp_path):
    from src.scenario_generator import generate_adversarial_feed
    base=write(tmp_path/'base.csv',[row(),row(2,'2026-01-02')])
    labels=generate_adversarial_feed(base,tmp_path/'qa',seed=42)
    with open(tmp_path/'qa'/'adversarial_feed.csv',newline='') as f:
        reader=csv.DictReader(f)
        assert reader.fieldnames==FIELDS and len(list(reader))==7
    assert len(labels['records'])==7

def test_invalid_encoding_is_failed_and_does_not_publish(tmp_path):
    c=setup(tmp_path);p=tmp_path/'invalid.csv';p.write_bytes(b'\xff\xfe')
    r=run_strategy(c,'full_refresh',str(p))
    assert r['status']=='FAILED' and snapshot(c,'full_refresh_orders')==[]

def test_null_field_is_quarantined(tmp_path):
    c=setup(tmp_path);p=tmp_path/'null.csv';p.write_text(','.join(FIELDS)+'\n1,2026-01-01,1,,NEW,2026-01-01T10:00:00Z\n')
    r=run_strategy(c,'full_refresh',str(p))
    assert r['rejected_count']==1 and c.execute('select count(*) from rejects').fetchone()[0]==1

def test_all_strategies_write_source_change_lineage(tmp_path):
    c=setup(tmp_path);p=write(tmp_path/'source.csv',[row()])
    for strategy in ['full_refresh','incremental_merge','partition_replacement']:
        r=run_strategy(c,strategy,p,changed_partitions=['2026-01-01'])
        n=c.execute('select count(*) from change_log where run_id=?',(r['run_id'],)).fetchone()[0]
        assert n>=1

def test_benchmark_with_rejected_input_cannot_pass(tmp_path):
    p=write(tmp_path/'bad.csv',[row(),row(2,amount='NaN')])
    report=benchmark(p,report_path=tmp_path/'bad-report.json',trials=1)
    assert report['comparison_passed'] is False

@pytest.mark.parametrize('strategy,target', [('full_refresh','full_refresh_orders'),('incremental_merge','incremental_orders'),('partition_replacement','partition_orders')])
def test_failure_and_retry_preserve_populated_target_for_each_strategy(tmp_path,strategy,target):
    c=setup(tmp_path);initial=write(tmp_path/'initial.csv',[row()])
    assert run_strategy(c,strategy,initial,changed_partitions=['2026-01-01'])['status']=='SUCCESS'
    before=snapshot(c,target)
    update=write(tmp_path/'next.csv',[row(2,'2026-01-02')])
    failed=run_strategy(c,strategy,update,changed_partitions=['2026-01-01','2026-01-02'],fail_before_commit=True)
    assert failed['status']=='FAILED' and snapshot(c,target)==before
    retried=run_strategy(c,strategy,update,changed_partitions=['2026-01-01','2026-01-02'])
    assert retried['status']=='SUCCESS'

@pytest.mark.parametrize('strategy', ['full_refresh','incremental_merge','partition_replacement'])
def test_empty_batch_semantics_for_each_strategy(tmp_path,strategy):
    c=setup(tmp_path);p=write(tmp_path/'empty.csv',[])
    r=run_strategy(c,strategy,p,changed_partitions=[] if strategy=='partition_replacement' else None)
    assert r['status']=='SUCCESS' and r['source_records']==0

def test_malformed_csv_retains_partial_source_count(tmp_path):
    c=setup(tmp_path);p=tmp_path/'partial.csv'
    p.write_text(','.join(FIELDS)+'\n1,2026-01-01,1,10,NEW,2026-01-01T10:00:00Z\n2,2026-01-02,1,20,NEW,"broken\n')
    r=run_strategy(c,'full_refresh',str(p))
    assert r['status']=='FAILED' and r['source_records']==1 and r['input_count']==1
    assert snapshot(c,'full_refresh_orders')==[]

def test_invalid_encoding_after_valid_record_retains_partial_count(tmp_path):
    c=setup(tmp_path);p=tmp_path/'partial-encoding.csv'
    p.write_bytes((',' .join(FIELDS)+'\n1,2026-01-01,1,10,NEW,2026-01-01T10:00:00Z\n').encode()+b'\xff\n')
    r=run_strategy(c,'full_refresh',str(p))
    assert r['status']=='FAILED' and r['source_records']==1
