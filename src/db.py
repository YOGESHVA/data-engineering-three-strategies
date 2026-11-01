import sqlite3
from pathlib import Path

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers(
      customer_id INTEGER PRIMARY KEY,
      customer_name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS source_orders(
      order_id INTEGER PRIMARY KEY,
      order_date TEXT NOT NULL,
      customer_id INTEGER NOT NULL,
      amount REAL NOT NULL CHECK(amount >= 0),
      status TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
    );
    CREATE TABLE IF NOT EXISTS full_refresh_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL,
      customer_id INTEGER NOT NULL, amount REAL NOT NULL,
      status TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS incremental_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL,
      customer_id INTEGER NOT NULL, amount REAL NOT NULL,
      status TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS partition_orders(
      order_id INTEGER PRIMARY KEY, order_date TEXT NOT NULL,
      customer_id INTEGER NOT NULL, amount REAL NOT NULL,
      status TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pipeline_runs(
      run_id TEXT PRIMARY KEY, strategy TEXT NOT NULL,
      started_at TEXT NOT NULL, ended_at TEXT,
      status TEXT NOT NULL, input_count INTEGER DEFAULT 0,
      output_count INTEGER DEFAULT 0, rejected_count INTEGER DEFAULT 0,
      duration_ms REAL, error_message TEXT
    );
    CREATE TABLE IF NOT EXISTS rejects(
      reject_id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL, source_file TEXT NOT NULL,
      raw_record TEXT NOT NULL, reason TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS change_log(
      change_id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL, operation TEXT NOT NULL,
      changed_at TEXT NOT NULL, source_file TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_source_date ON source_orders(order_date);
    CREATE INDEX IF NOT EXISTS idx_partition_date ON partition_orders(order_date);
    """)
    return conn

def seed_customers(conn, rows):
    conn.executemany("INSERT OR IGNORE INTO customers VALUES (?,?)", rows)
    conn.commit()
