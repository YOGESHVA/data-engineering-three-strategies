import csv
from src.db import connect,seed_customers
from src.strategies import run_strategy,snapshot

FIELDS=["order_id","order_date","customer_id","amount","status","updated_at"]

def write(path,rows):
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    return str(path)

def setup(tmp_path):
    conn=connect(tmp_path/"test.db")
    seed_customers(conn,[(1,"A"),(2,"B")])
    return conn

def test_three_strategies_same_snapshot(tmp_path):
    conn=setup(tmp_path)
    rows=[
      dict(order_id=1,order_date="2026-01-01",customer_id=1,amount=100,status="NEW",updated_at="2026-01-01T10:00:00"),
      dict(order_id=2,order_date="2026-01-02",customer_id=2,amount=200,status="PAID",updated_at="2026-01-02T10:00:00")]
    path=write(tmp_path/"source.csv",rows)
    for s in ["full_refresh","incremental_merge","partition_replacement"]:
        r=run_strategy(conn,s,path,changed_partitions=["2026-01-01","2026-01-02"])
        assert r["status"]=="SUCCESS"
    a=snapshot(conn,"full_refresh_orders")
    b=snapshot(conn,"incremental_orders")
    c=snapshot(conn,"partition_orders")
    assert a==b==c
    conn.close()

def test_incremental_rerun_is_idempotent(tmp_path):
    conn=setup(tmp_path)
    rows=[dict(order_id=1,order_date="2026-01-01",customer_id=1,amount=100,status="NEW",updated_at="2026-01-01T10:00:00")]
    path=write(tmp_path/"source.csv",rows)
    run_strategy(conn,"incremental_merge",path)
    run_strategy(conn,"incremental_merge",path)
    assert len(snapshot(conn,"incremental_orders"))==1
    conn.close()

def test_invalid_customer_is_quarantined(tmp_path):
    conn=setup(tmp_path)
    rows=[dict(order_id=1,order_date="2026-01-01",customer_id=999,amount=100,status="NEW",updated_at="2026-01-01T10:00:00")]
    path=write(tmp_path/"bad.csv",rows)
    r=run_strategy(conn,"full_refresh",path)
    assert r["rejected_count"]==1
    assert conn.execute("SELECT COUNT(*) FROM rejects").fetchone()[0]==1
    conn.close()

def test_failed_load_rolls_back_target(tmp_path):
    conn=setup(tmp_path)
    rows=[dict(order_id=1,order_date="2026-01-01",customer_id=1,amount=100,status="NEW",updated_at="2026-01-01T10:00:00")]
    path=write(tmp_path/"source.csv",rows)
    r=run_strategy(conn,"full_refresh",path,fail_before_commit=True)
    assert r["status"]=="FAILED"
    assert len(snapshot(conn,"full_refresh_orders"))==0
    conn.close()

def test_empty_input(tmp_path):
    conn=setup(tmp_path)
    path=write(tmp_path/"empty.csv",[])
    r=run_strategy(conn,"incremental_merge",path)
    assert r["status"]=="SUCCESS"
    assert r["input_count"]==0
    conn.close()



def test_conflicting_duplicate_order_ids_are_rejected(tmp_path):
    conn = setup(tmp_path)

    rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=100,
            status="NEW",
            updated_at="2026-01-01T10:00:00"
        ),
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=500,
            status="PAID",
            updated_at="2026-01-01T11:00:00"
        )
    ]

    path = write(tmp_path / "duplicates.csv", rows)

    result = run_strategy(conn, "full_refresh", path)

    assert result["rejected_count"] == 1
    assert len(snapshot(conn, "full_refresh_orders")) == 1

    conn.close()

def test_missing_amount_is_rejected(tmp_path):
    conn = setup(tmp_path)

    rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount="",
            status="NEW",
            updated_at="2026-01-01T10:00:00"
        )
    ]

    path = write(tmp_path / "missing_amount.csv", rows)

    result = run_strategy(conn, "full_refresh", path)

    assert result["rejected_count"] == 1
    assert len(snapshot(conn, "full_refresh_orders")) == 0

    conn.close()

def test_malformed_order_date_is_rejected(tmp_path):
    conn = setup(tmp_path)

    rows = [
        dict(
            order_id=1,
            order_date="not-a-date",
            customer_id=1,
            amount=100,
            status="NEW",
            updated_at="2026-01-01T10:00:00"
        )
    ]

    path = write(tmp_path / "malformed_date.csv", rows)

    result = run_strategy(conn, "full_refresh", path)

    assert result["rejected_count"] == 1
    assert len(snapshot(conn, "full_refresh_orders")) == 0

    conn.close()
def test_zero_amount_is_accepted(tmp_path):
    conn = setup(tmp_path)

    rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=0,
            status="NEW",
            updated_at="2026-01-01T10:00:00"
        )
    ]

    path = write(tmp_path / "zero_amount.csv", rows)

    result = run_strategy(conn, "full_refresh", path)

    assert result["rejected_count"] == 0

    record = snapshot(conn, "full_refresh_orders")
    assert len(record) == 1
    assert record[0][3] == 0.0

    conn.close()
def test_invalid_order_status_is_rejected(tmp_path):
    conn = setup(tmp_path)

    rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=100,
            status="UNKNOWN_STATUS",
            updated_at="2026-01-01T10:00:00"
        )
    ]

    path = write(tmp_path / "invalid_status.csv", rows)

    result = run_strategy(conn, "full_refresh", path)

    assert result["rejected_count"] == 1
    assert len(snapshot(conn, "full_refresh_orders")) == 0

    conn.close()


def test_older_update_does_not_overwrite_newer_record(tmp_path):
    conn = setup(tmp_path)

    newer_rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=4200,
            status="PLACED",
            updated_at="2026-11-01T12:00:00"
        )
    ]

    newer_path = write(tmp_path / "newer.csv", newer_rows)

    run_strategy(conn, "incremental_merge", newer_path)

    older_rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=9999,
            status="CANCELLED",
            updated_at="2026-10-31T12:00:00"
        )
    ]

    older_path = write(tmp_path / "older.csv", older_rows)

    result = run_strategy(
        conn,
        "incremental_merge",
        older_path
    )

    record = snapshot(conn, "incremental_orders")

    assert result["status"] == "SUCCESS"
    assert result["rejected_count"] == 0
    assert len(record) == 1
    assert record[0][3] == 4200.0
    assert record[0][4] == "PLACED"
    assert record[0][5] == "2026-11-01T12:00:00"

    conn.close()

def test_late_arriving_order_is_loaded_by_all_strategies(tmp_path):
    conn = setup(tmp_path)

    initial_rows = [
        dict(
            order_id=1,
            order_date="2026-01-01",
            customer_id=1,
            amount=1000,
            status="PLACED",
            updated_at="2026-01-01T10:00:00"
        )
    ]

    initial_path = write(tmp_path / "initial.csv", initial_rows)

    run_strategy(conn, "full_refresh", initial_path)
    run_strategy(conn, "incremental_merge", initial_path)
    run_strategy(
        conn,
        "partition_replacement",
        initial_path,
        changed_partitions=["2026-01-01"]
    )

    late_rows = [
        dict(
            order_id=2,
            order_date="2025-12-31",
            customer_id=1,
            amount=2000,
            status="PLACED",
            updated_at="2026-01-02T10:00:00"
        )
    ]

    late_path = write(tmp_path / "late.csv", late_rows)

    full_rows = initial_rows + late_rows
    full_path = write(tmp_path / "full_late.csv", full_rows)

    run_strategy(conn, "full_refresh", full_path)
    run_strategy(conn, "incremental_merge", late_path)
    run_strategy(
        conn,
        "partition_replacement",
        late_path,
        changed_partitions=["2025-12-31"]
    )

    full_result = snapshot(conn, "full_refresh_orders")
    incremental_result = snapshot(conn, "incremental_orders")
    partition_result = snapshot(conn, "partition_orders")

    assert len(full_result) == 2
    assert full_result == incremental_result
    assert full_result == partition_result

    conn.close()
