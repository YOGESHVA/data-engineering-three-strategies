import sqlite3
from pathlib import Path


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers(
      customer_id INTEGER PRIMARY KEY, customer_name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS source_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, customer_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount >= 0), status TEXT NOT NULL CHECK(status IN ('PLACED','SHIPPED','DELIVERED','CANCELLED','NEW','PAID')), updated_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(customer_id));
    CREATE TABLE IF NOT EXISTS full_refresh_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, customer_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount >= 0), status TEXT NOT NULL CHECK(status IN ('PLACED','SHIPPED','DELIVERED','CANCELLED','NEW','PAID')), updated_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(customer_id));
    CREATE TABLE IF NOT EXISTS incremental_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, customer_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount >= 0), status TEXT NOT NULL CHECK(status IN ('PLACED','SHIPPED','DELIVERED','CANCELLED','NEW','PAID')), updated_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(customer_id));
    CREATE TABLE IF NOT EXISTS partition_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL, customer_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount >= 0), status TEXT NOT NULL CHECK(status IN ('PLACED','SHIPPED','DELIVERED','CANCELLED','NEW','PAID')), updated_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(customer_id));
    CREATE TABLE IF NOT EXISTS pipeline_runs(
      run_id TEXT PRIMARY KEY, strategy TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
      status TEXT NOT NULL, input_count INTEGER DEFAULT 0, output_count INTEGER DEFAULT 0,
      rejected_count INTEGER DEFAULT 0, duration_ms REAL, error_message TEXT,
      source_file TEXT, source_sha256 TEXT, input_mode TEXT, partition_scope TEXT, accepted_count INTEGER DEFAULT 0, duplicate_count INTEGER DEFAULT 0, stale_count INTEGER DEFAULT 0, unchanged_count INTEGER DEFAULT 0, inserted_count INTEGER DEFAULT 0, updated_count INTEGER DEFAULT 0, deleted_count INTEGER DEFAULT 0, ignored_scope_count INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS rejects(
      reject_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, source_file TEXT NOT NULL,
      raw_record TEXT NOT NULL, reason TEXT NOT NULL, source_record_number INTEGER,
      FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id));
    CREATE TABLE IF NOT EXISTS change_log(
      change_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
      operation TEXT NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')), changed_at TEXT NOT NULL, source_file TEXT NOT NULL,
      source_sha256 TEXT, run_id TEXT, source_record_number INTEGER, old_values TEXT, new_values TEXT,
      FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id));
    CREATE INDEX IF NOT EXISTS idx_source_date ON source_orders(order_date);
    CREATE INDEX IF NOT EXISTS idx_partition_date ON partition_orders(order_date);
    CREATE INDEX IF NOT EXISTS idx_incremental_date ON incremental_orders(order_date);
    """)
    # Additive migration for databases created by earlier versions.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pipeline_runs)")}
    for name, decl in [("source_file", "TEXT"), ("source_sha256", "TEXT"), ("input_mode", "TEXT"), ("partition_scope", "TEXT"), ("accepted_count", "INTEGER DEFAULT 0"), ("duplicate_count", "INTEGER DEFAULT 0"), ("stale_count", "INTEGER DEFAULT 0"), ("unchanged_count", "INTEGER DEFAULT 0"), ("inserted_count", "INTEGER DEFAULT 0"), ("updated_count", "INTEGER DEFAULT 0"), ("deleted_count", "INTEGER DEFAULT 0"), ("ignored_scope_count", "INTEGER DEFAULT 0")]:
        if name not in cols:
            conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {name} {decl}")
    reject_cols = {r[1] for r in conn.execute("PRAGMA table_info(rejects)")}
    if "source_record_number" not in reject_cols:
        conn.execute("ALTER TABLE rejects ADD COLUMN source_record_number INTEGER")
    change_cols = {r[1] for r in conn.execute("PRAGMA table_info(change_log)")}
    for name, decl in [("source_sha256", "TEXT"), ("run_id", "TEXT"), ("source_record_number", "INTEGER"), ("old_values", "TEXT"), ("new_values", "TEXT")]:
        if name not in change_cols:
            conn.execute(f"ALTER TABLE change_log ADD COLUMN {name} {decl}")
    conn.commit()
    return conn


def seed_customers(conn, rows):
    conn.executemany("INSERT OR IGNORE INTO customers VALUES (?,?)", rows)
    conn.commit()
