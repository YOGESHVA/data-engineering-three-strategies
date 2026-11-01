# Data Loading Strategies — Full Refresh, Merge and Partition Replacement

> This project is a local Python/SQLite prototype. It does not claim lakehouse-scale performance.

## Clean setup and verification

Clone the repository first (or extract the supplied project ZIP):

```bash
git clone https://github.com/YOGESHVA/data-engineering-three-strategies.git
cd data-engineering-three-strategies
```

Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m python -m pytest -q
python -m src.demo
```

The automated suite is collected only from `tests/`; manual demonstrations live under `src/manual_*.py` and execute only when run directly. Input timestamps must be ISO-8601 timezone-aware values (for example `2026-01-01T10:00:00Z`). CSV headers must exactly match the documented six-column schema. Non-finite and negative amounts are rejected.

# Three Data Loading Strategies — Comparison Project



## 1. Business Objective



The objective of this project is to compare three different data loading strategies used to publish data into analytical target tables:



1. Full Refresh

2. Incremental Merge

3. Partition Replacement



The project uses the same order dataset to evaluate the three strategies.



It verifies that all three target tables contain equivalent final records and compares their:



- Execution time

- Input and output row counts

- Rejected records

- Pipeline execution status

- Failure recovery

- Data consistency



The main goal is to understand which loading strategy is suitable for different data engineering scenarios.



---



## 2. Technology Stack



| Technology | Purpose |

|---|---|

| Python 3.10+ | Data processing and pipeline logic |

| SQLite | Source reference data, target tables, and execution logs |

| CSV | Input datasets |

| pytest | Automated testing |

| pandas | Optional data analysis and extensions |

| Git | Version control |



The core pipeline uses Python's built-in `csv` and `sqlite3` modules.



---



## 3. Dataset Definition



**Dataset:** Orders



**Grain:** One row represents one current order.



**Primary Key:** `order_id`



**Partition Key:** `order_date`



**Relationship:** Many orders can belong to one customer.



### Source schema



| Column | Description |

|---|---|

| order_id | Unique order identifier |

| order_date | Date when the order was placed |

| customer_id | Customer identifier |

| amount | Order amount |

| status | Current order status |

| updated_at | Timestamp of the latest update |



### Business validation rules



- Order ID must be a positive integer.

- Customer ID must exist in the customer reference table.

- Amount must be zero or greater.

- Status must not be empty and must belong to the accepted status values.

- Order date must follow YYYY-MM-DD format.

- Updated timestamp must be a valid ISO timestamp.

- Exact duplicate records are removed during validation.

- Conflicting records with the same order ID are rejected.



### Data assumptions



The three-strategy comparison uses a complete current-state snapshot for the initial load.



For subsequent loads:



- Full refresh receives the complete current-state dataset.

- Incremental merge receives changed or new records.

- Partition replacement receives the complete contents of every affected partition.



The incremental merge uses `order_id` as its business key and `updated_at` to prevent older updates from overwriting newer records.



For production-grade deletion handling, explicit CDC tombstones or a change feed should be used.



---



## 4. Project Architecture



```text

&#x20;               CSV Dataset

&#x20;                    |

&#x20;                    v

&#x20;             Read Source Data

&#x20;                    |

&#x20;                    v

&#x20;             Data Validation

&#x20;                    |

&#x20;            +-------+-------+

&#x20;            |       |       |

&#x20;            v       v       v

&#x20;         Full   Incremental  Partition

&#x20;        Refresh    Merge   Replacement

&#x20;            |       |       |

&#x20;            v       v       v

&#x20;         Target  Target   Target

&#x20;         Table   Table    Table

&#x20;            |       |       |

&#x20;            +-------+-------+

&#x20;                    |

&#x20;                    v

&#x20;            Data Reconciliation

&#x20;                    |

&#x20;                    v

&#x20;          Compare Final Row Sets

&#x20;                    |

&#x20;                    v

&#x20;            Performance Report

&#x20;                    |

&#x20;                    v

&#x20;          Runtime and Row Counts

```



Each strategy writes to an independent SQLite target table.



The final results are compared to confirm that all three strategies produce equivalent data.



---



## 5. Project Folder Structure



```text

Data Engineering Project/

│

├── data/

│   ├── generated/

│   ├── batch2/

│   ├── scenario/

│   └── sample/

│

├── reports/

│   └── strategy_comparison.json

│

├── sql/

│

├── src/

│   ├── __init__.py

│   ├── db.py

│   ├── strategies.py

│   ├── benchmark.py

│   ├── data_generator.py

│   └── demo.py

│

├── tests/

│   └── test_strategies.py

│

├── DESIGN_TRADEOFFS.md

├── README.md

├── requirements.txt

└── .gitignore

```



Additional scripts and datasets may be present for batch processing and manual edge-case testing.



---



## 6. Environment Setup



### Create a virtual environment



```powershell

py -m venv .venv

```



### Activate the environment



```powershell

.venv\Scripts\activate

```



### Install dependencies



```powershell

pip install -r requirements.txt

```



If `py` is unavailable, use `python` instead.



---



## 7. Run the Project



### Run the demo



```powershell

python -m src.demo

```



The demo demonstrates multiple data batches, including an updated order and a new order, and compares the final results.



### Generate 100,000 records



```powershell

python -m src.data_generator --rows 100000 --seed 42

```



The fixed seed makes the generated dataset reproducible.



### Run the benchmark



```powershell

python -m src.benchmark --input data/generated/orders.csv --trials 3 --report reports/strategy_comparison.json

```



The benchmark records execution time, row counts, and result equivalence.



### Run automated tests



```powershell

python -m pytest -q

```



---



## 8. Three Data Loading Strategies



### Strategy 1: Full Refresh



Full refresh deletes the existing target records and reloads the complete source dataset.



**Process:**



1. Read the source CSV.

2. Validate the records.

3. Delete existing target records.

4. Insert all valid source records.

5. Commit the transaction.



**Advantages:**



- Simple implementation.

- Easy to understand and maintain.

- Naturally removes records missing from the complete source snapshot.

- Useful when the dataset is relatively small.



**Disadvantages:**



- Reloads all records even when only a few records change.

- Requires more repeated I/O.

- Can take longer for large datasets.



**Real-world example:**



A company reloads its complete monthly sales dataset into a reporting table every month.



### Strategy 2: Incremental Merge



Incremental merge inserts new records and updates existing records using a business key.



In this project, `order_id` is the business key.



**Process:**



1. Read changed or new records.

2. Validate the incoming data.

3. Check whether the order already exists.

4. Insert new records.

5. Update existing records when the incoming `updated_at` is not older.

6. Commit the transaction.



**Advantages:**



- Processes only changed or new records.

- Efficient when the change volume is small.

- Supports safe reruns.

- Prevents stale updates from overwriting newer records.



**Disadvantages:**



- Requires reliable change detection.

- Requires update timestamp or version management.

- Deletion handling needs an explicit mechanism such as CDC.



**Real-world example:**



An e-commerce company receives new orders and order-status updates throughout the day. Instead of reloading all orders, it processes only the changed records.



### Strategy 3: Partition Replacement



Partition replacement deletes and reloads only the affected partitions.



In this project, `order_date` is the partition key.



**Process:**



1. Identify affected order dates.

2. Read complete records for those dates.

3. Validate the records.

4. Delete existing records from the affected partitions.

5. Insert the complete replacement partition data.

6. Commit the transaction.



**Advantages:**



- Avoids reloading unaffected partitions.

- Useful when data changes are concentrated in specific dates.

- Supports historical corrections and backfills.



**Disadvantages:**



- Requires complete data for every affected partition.

- An incorrect partition list can leave stale records.

- Reloading a large partition can be expensive.



**Real-world example:**



A company discovers incorrect sales records for one day. It reloads that day's complete sales partition instead of refreshing the entire historical dataset.



---



## 9. Strategy Comparison



| Comparison | Full Refresh | Incremental Merge | Partition Replacement |

|---|---|---|---|

| Loading method | Reload all records | Insert and update changed records | Reload affected partitions |

| Processing volume | Entire dataset | Changed records | Complete affected partitions |

| New records | Supported | Supported | Supported |

| Updated records | Supported | Supported | Supported |

| Historical corrections | Complete reload | Updated record | Replace affected partition |

| Delete handling | Missing snapshot records are removed | Requires CDC or tombstones | Removed within replaced partitions |

| Rerun safety | Supported | Supported | Supported with complete partitions |

| Best use case | Small or complete datasets | Small change volumes | Date-based or partitioned data |



---



## 10. Data Quality and Traceability



Data validation is performed before publishing records into target tables.



The pipeline handles:



- Missing values

- Malformed dates and timestamps

- Invalid order IDs

- Unknown customers

- Negative amounts

- Invalid order statuses

- Exact duplicate records

- Conflicting duplicate order IDs



Rejected records are stored in the `rejects` table with:



- Run ID

- Source file

- Raw record

- Rejection reason



This provides traceability and makes it easier to investigate data quality issues.



---



## 11. Pipeline Execution Tracking



Each pipeline execution is recorded in the `pipeline_runs` table.



The execution log tracks:



- Run ID

- Loading strategy

- Execution status

- Input row count

- Output row count

- Rejected row count

- Execution duration

- Error details



The pipeline uses execution statuses such as:



- RUNNING

- SUCCESS

- FAILED



This helps monitor pipeline execution and investigate failures.



---



## 12. Idempotency



Idempotency means that running the same input multiple times should not create duplicate records or change the final result unexpectedly.



This project verifies rerun safety for all three strategies.



**Full refresh:** Reloading the same complete snapshot produces the same target records.



**Incremental merge:** The business key prevents duplicate orders, and timestamp comparison prevents stale updates.



**Partition replacement:** Replacing the same complete affected partitions produces the same final partition contents.



Idempotency is important because data pipelines may need to be restarted after failures.



---



## 13. Late-Arriving Data



Sometimes an order arrives after its original order date.



For example:



- Order date: 2025-12-31

- Arrival date: 2026-01-02



The order arrives late, but it still belongs to the December 31 partition.



The project tests this scenario.



**How the strategies handle it:**



- Full refresh reloads the complete snapshot containing the late order.

- Incremental merge inserts the late-arriving order using its order ID.

- Partition replacement reloads the complete affected historical partition.



After loading, the three target tables are reconciled to confirm equivalent results.



---



## 14. Out-of-Order Updates



An older update may arrive after a newer update for the same order.



For example:



| Update | Amount | Updated timestamp |

|---|---:|---|

| Newer update | 4200 | 2026-11-01 12:00 |

| Older update | 9999 | 2026-10-31 12:00 |



If the older update is applied, it can overwrite correct information.



The incremental merge compares the incoming `updated_at` with the existing target timestamp.



Only an incoming record with a timestamp greater than or equal to the existing timestamp is applied.



This prevents older updates from overwriting newer records.



The project includes an automated test for this scenario.



---



## 15. Failure Recovery and Retry



Each strategy performs target-table changes inside a database transaction.



If a simulated failure occurs before the transaction commits:



1. The transaction is rolled back.

2. Incomplete target changes are not published.

3. The failed execution remains visible in the run log.

4. The issue can be investigated.

5. The same input can be retried after correcting the cause.



For production systems, additional features should include:



- Immutable source snapshots

- Stable run IDs

- Checkpoint metadata

- Structured error logging

- Retry policies

- Explicit CDC events for deletions



---



## 16. Backfill Strategy



Backfill means reprocessing historical data to correct missing or incorrect records.



For example, if order records for a historical date are incorrect:



1. Identify the affected date range.

2. Obtain the complete source data for those dates.

3. Identify the affected partitions.

4. Run partition replacement using complete partition data, or perform a full refresh using a complete current-state snapshot.

5. Compare the final target records.

6. Check rejected records and execution logs.



A successful backfill should produce consistent results across the three target tables.



---



## 17. Performance Measurement



The project uses Python's `time.perf_counter()` to measure execution time.



The benchmark records:



- Strategy name

- Execution duration

- Input row count

- Output row count

- Rejected row count

- Final result equivalence



The benchmark writes its output to:



`reports/strategy_comparison.json`



### Latest 100,000-row first-load benchmark (3-trial median)



| Strategy | Input rows | Output rows | Runtime |

|---|---:|---:|---:|

| Full Refresh | 100,000 | 100,000 | 2,491.712 ms |

| Incremental Merge | 100,000 | 100,000 | 2,812.496 ms |

| Partition Replacement | 100,000 | 100,000 | 2,832.157 ms |



**Reconciliation result:** All three strategies produced equivalent results.



These are the measured 3-trial medians recorded in `reports/strategy_comparison.json`. Use `reports/later_batch_comparison.json` for the separate later-batch comparison. Timings are local SQLite observations, not universal performance guarantees.



For a fairer comparison:



- Start with equivalent initial conditions.

- Run multiple trials.

- Compare median execution time.

- Keep the source data consistent.

- Compare final target results, not just runtime.



### Important benchmark interpretation



The first-load benchmark uses the same 100,000-row snapshot for all three strategies.



For subsequent loads, the amount of input data differs:



- Full refresh receives the complete snapshot.

- Incremental merge receives changed records.

- Partition replacement receives complete affected partitions.



These results should be reported separately because they represent different workloads.



---



## 18. Automated Test Coverage



The project contains 59 automated tests using pytest.



The tests cover:



1. Equivalence of all three strategies.

2. Incremental rerun idempotency.

3. Rejection of unknown customers.

4. Failed-load transaction rollback.

5. Empty input handling.

6. Conflicting duplicate order IDs.

7. Missing amount validation.

8. Malformed order date validation.

9. Zero amount boundary case.

10. Invalid order status.

11. Older updates not overwriting newer records.

12. Late-arriving orders loaded by all three strategies.



### Latest test execution

```text
59 passed in the latest clean verification run
```

**Test result:** All 59 automated tests passed in the latest verified run.


---



## 19. Limitations and Production Improvements



This project is a local data engineering benchmark using Python and SQLite.



It does not represent the performance of a distributed warehouse or lakehouse platform.



### Current limitations



- SQLite is used instead of a distributed analytical database.

- The benchmark runs locally.

- Incremental merge uses `updated_at` for update ordering.

- Explicit CDC deletion events are not implemented.

- Partition replacement depends on complete affected partition data.

- Production orchestration and checkpoint management are outside the current scope.



### Future improvements



A production-grade implementation could include:



- Apache Spark or PySpark for distributed processing.

- Cloud data warehouses such as Snowflake or BigQuery.

- Apache Airflow for pipeline orchestration.

- Structured logging and monitoring.

- Schema versioning.

- Source checkpoints and CDC.

- Automated data quality monitoring.

- Warehouse-specific partition management.



---



## 20. Final Conclusion



This project demonstrates three important data loading strategies and compares their performance, reliability, and data consistency.



**Full Refresh** is simple and useful when the complete dataset needs to be reloaded.



**Incremental Merge** is suitable when only a small number of records change and efficient processing is important.



**Partition Replacement** is useful when historical data corrections or changes are limited to specific partitions.



The project also demonstrates important data engineering concepts such as:



- Data validation

- Data reconciliation

- Idempotency

- Transaction management

- Failure recovery

- Late-arriving data

- Out-of-order updates

- Backfill processing

- Performance benchmarking

- Automated testing



The final results confirm that all three strategies can produce equivalent target data when their input assumptions are satisfied.



---



## 21. Submission Checklist



- [x] Run the complete project demo.

- [x] Verify equivalent results across all three strategies.

- [x] Generate the 100,000-row dataset.

- [x] Run the performance benchmark.

- [x] Save the benchmark JSON report.

- [x] Run all automated tests.

- [x] Verify late-arriving data handling.

- [x] Verify out-of-order update handling.

- [x] Review failure recovery and retry behavior.

- [ ] Review backfill documentation.

- [ ] Prepare the final project presentation.

- [ ] Explain the advantages and trade-offs of each strategy.



**Project status:** All 59 automated tests pass; demo, initial-load benchmark, later-batch benchmark, and SQL schema checks are verified.


## Later-batch benchmark (representative workload)

The initial-load benchmark is useful for setup cost, but it does not represent later
loads. Generate a deterministic base snapshot, a small change feed, a complete snapshot
of affected partitions, and an independent expected final state:

```bash
python -m src.scenario_generator --output data/scenario --base-rows 1000 --updates 50 --inserts 50 --seed 42
python -m src.later_batch_benchmark --output data/scenario --base-rows 1000 --updates 50 --inserts 50 --seed 42 --trials 3
```

The later-batch benchmark starts each strategy from the same base state. Full refresh
receives the complete final snapshot; incremental merge receives only updates/inserts;
partition replacement receives complete rows for each affected date. It verifies each
result against `expected_final.csv` and reports median timings over repeated trials.
Deletion CDC is not implemented for incremental merge; do not use this benchmark to
claim deletion equivalence.

For the initial-load benchmark:

```bash
python -m src.benchmark --input data/sample/orders_full.csv --trials 3 --report reports/strategy_comparison.json
```

An existing `--db` path is protected by default. Use `--reset` only when you explicitly
intend to delete that benchmark database. The report path is configurable.

## Row accounting and operational semantics

Each run records physical `source_records`, accepted unique rows, exact duplicates,
rejected rows, stale updates, unchanged/equal-version rows, inserted/updated/deleted
rows, ignored out-of-scope rows, and target row count after the run. `input_count` is
retained as a compatibility alias for physical source records. For every parsed file:

`source_records = accepted_unique + exact_duplicates + rejected_records`

Target cardinality is reconciled independently as `target_after = target_before +
inserts - deletes`; updates do not change cardinality. Full refresh and partition
replacement are snapshot operations, not CDC deletion feeds. An explicitly empty
`changed_partitions=[]` is a no-op; `None` derives partitions from valid input. Moving
an order between dates requires both old and new dates in the replacement scope.
Partition replacement aborts when any source row is rejected to avoid publishing an
incomplete partition snapshot.

## Data dictionary

| Field | Type / rule | Meaning |
|---|---|---|
| `order_id` | Positive integer, primary key | One order at the target grain |
| `order_date` | Canonical `YYYY-MM-DD` | Business/partition date |
| `customer_id` | Positive integer, FK to `customers` | Customer owning the order |
| `amount` | Non-negative decimal input, max 2 fractional digits | Order amount; stored as SQLite numeric |
| `status` | `PLACED`, `SHIPPED`, `DELIVERED`, `CANCELLED`, `NEW`, `PAID` | Order state |
| `updated_at` | ISO-8601 with timezone, normalized to UTC microseconds | Version timestamp used by merge |
| `run_id` | UUID primary key in `pipeline_runs` | One execution attempt |
| `source_sha256` | SHA-256 hex digest | Fingerprint of exact source bytes |

SQLite target constraints enforce primary keys, customer foreign keys, non-null fields,
non-negative amounts and allowed statuses. `sql/schema.sql` is the reference DDL;
`src/db.py` is the executable initializer and includes additive migrations for older
local databases. For a clean review, use a new database file so all constraints are
created from the current schema.

The current later-batch report uses a 1,000-row base, 50 updates, 50 inserts and two affected dates (250 complete replacement rows). Its recorded three-trial median timings are approximately 38.635 ms for full refresh, 6.390 ms for incremental merge and 12.124 ms for partition replacement. These are machine-specific observations; the JSON report is the authoritative evidence.
