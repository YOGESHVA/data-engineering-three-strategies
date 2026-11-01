# Three Data Loading Strategies — Comparison Project

## 1\. Project Overview

This project compares three common data ingestion strategies for loading order data into analytical target tables:

1. **Full Refresh**
2. **Incremental Merge**
3. **Partition Replacement**

All three strategies process the same order dataset. The project checks whether they produce equivalent final records and compares their execution time, row counts, rejected records, and execution status.

The goal is to understand the strengths, limitations, and suitable use cases of each loading strategy.

## 2\. Technology Stack

|Technology|Purpose|
|-|-|
|Python 3.10+|Data processing and pipeline logic|
|SQLite|Source reference data, target tables, and execution logs|
|CSV|Input datasets|
|pytest|Automated testing|
|Git and GitHub|Version control and project hosting|

The core pipeline uses Python's built-in `csv` and `sqlite3` modules.

## 3\. Dataset

**Dataset:** Orders

**Grain:** One row represents one current order.

**Business key:** `order\\\_id`

**Partition key:** `order\\\_date`

### Main columns

|Column|Description|
|-|-|
|`order\\\_id`|Unique order identifier|
|`order\\\_date`|Date when the order was placed|
|`customer\\\_id`|Customer identifier|
|`amount`|Order amount|
|`status`|Current order status|
|`updated\\\_at`|Timestamp of the latest update|

### Data validation

The pipeline validates incoming records before publishing them to the target tables. Validation includes checks for:

* Positive order IDs
* Existing customer IDs
* Non-negative amounts
* Accepted, non-empty order statuses
* Valid order dates and timestamps
* Exact duplicate records
* Conflicting records with the same order ID

Invalid records are rejected rather than silently loaded.

### Loading assumptions

* The initial load uses a complete current-state snapshot.
* Full Refresh receives the complete current-state dataset.
* Incremental Merge receives new or changed records.
* Partition Replacement receives the complete contents of each affected partition.
* Incremental Merge uses `order\\\_id` as its business key and `updated\\\_at` to prevent older updates from overwriting newer records.

For production-grade deletion handling, an explicit CDC event or tombstone mechanism would be needed.

## 4\. Project Architecture

```text
                  CSV Dataset
                       |
                       v
                Read Source Data
                       |
                       v
                 Data Validation
                       |
          +------------+------------+
          |            |            |
          v            v            v
      Full Refresh  Incremental  Partition
                       Merge    Replacement
          |            |            |
          v            v            v
      Target Table  Target Table  Target Table
          |            |            |
          +------------+------------+
                       |
                       v
               Data Reconciliation
                       |
                       v
              Compare Final Records
                       |
                       v
                Performance Report
```

Each strategy writes to an independent SQLite target table. The final records are reconciled to check that all three strategies produce equivalent results.

## 5\. Repository Structure

The repository contains the project data, Python source code, tests, SQL resources, reports, and project documentation.

```text
Data Engineering Project/
│
├── data/
│   ├── generated/
│   ├── batch2/
│   └── sample.csv
│
├── reports/
│
├── sql/
│
├── src/
│   ├── \\\_\\\_init\\\_\\\_.py
│   ├── db.py
│   ├── strategies.py
│   ├── benchmark.py
│   ├── later\\\_batch\\\_benchmark.py
│   ├── data\\\_generator.py
│   └── demo.py
│
├── tests/
│
├── DESIGN\\\_TRADEOFFS.md
├── README.md
├── requirements.txt
└── .gitignore
```

This is a representative project layout. If your local repository contains additional scripts or data files, keep those files in their existing locations.

## 6\. Environment Setup

### Step 1: Create a virtual environment

```bash
py -m venv .venv
```

If the `py` command is unavailable, use:

```bash
python -m venv .venv
```

### Step 2: Activate the environment on Windows

```bash
.venv\\\\Scripts\\\\activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

## 7\. Run the Project

Run these commands from the project root directory.

### Run the demo

```bash
python -m src.demo
```

The demo runs the loading strategies and compares their final results.

### Generate a dataset

If you want to generate a 100,000-row dataset:

```bash
python -m src.data\\\_generator --rows 100000 --seed 42
```

The fixed seed makes the generated data reproducible.

### Run the automated tests

```bash
python -m pytest -q
```

**Latest locally reported test result:**

```text
59 passed in 127.11s
```

This result reflects the test run performed locally on Windows. Test duration may differ on another machine.

### Run the later-batch benchmark

```bash
python -m src.later\\\_batch\\\_benchmark --base-rows 1000 --updates 50 --inserts 50 --seed 42 --trials 3 --report reports/later\\\_batch\\\_comparison.json
```

This benchmark is intended to compare strategies for a later batch containing updates and inserts. Use the generated report for the actual measurements from your machine.

## 8\. The Three Data Loading Strategies

### Strategy 1: Full Refresh

Full Refresh deletes the existing target data and reloads the complete source dataset.

**Process:**

1. Read the complete source dataset.
2. Validate the records.
3. Delete the existing target records.
4. Insert all valid source records.
5. Commit the transaction.

**Advantages:**

* Simple to implement and understand.
* Easy to maintain.
* Removes records that are no longer present in the complete source snapshot.
* Useful for relatively small datasets.

**Disadvantages:**

* Reloads all records even when only a few records have changed.
* Repeats more input/output work.
* Can take longer as the dataset grows.

**Example:** A company reloads its complete monthly sales dataset into a reporting table.

### Strategy 2: Incremental Merge

Incremental Merge inserts new records and updates existing records using a business key.

In this project, `order\\\_id` is the business key.

**Process:**

1. Read new or changed records.
2. Validate the incoming data.
3. Match records using `order\\\_id`.
4. Insert new records.
5. Update existing records when the incoming timestamp is not older.
6. Commit the transaction.

**Advantages:**

* Processes only new or changed records.
* Efficient when the change volume is small.
* Supports safe reruns.
* Timestamp comparison protects against stale updates.

**Disadvantages:**

* Requires reliable change detection.
* Requires timestamp or version management.
* Deletion handling needs an explicit mechanism such as CDC.

**Example:** An e-commerce company processes new orders and order-status changes throughout the day instead of reloading its entire order history.

### Strategy 3: Partition Replacement

Partition Replacement deletes and reloads only the affected partitions.

In this project, `order\\\_date` is the partition key.

**Process:**

1. Identify affected order dates.
2. Obtain the complete data for those partitions.
3. Validate the records.
4. Delete the existing records in the affected partitions.
5. Insert the replacement partition data.
6. Commit the transaction.

**Advantages:**

* Avoids reloading unaffected partitions.
* Useful when changes are concentrated in specific dates.
* Supports historical corrections and backfills.

**Disadvantages:**

* Requires complete data for every affected partition.
* An incorrect partition list can leave stale records.
* Replacing a large partition can be expensive.

**Example:** A company corrects sales data for one day and reloads that day's complete partition instead of refreshing all historical data.

## 9\. Strategy Comparison

|Comparison|Full Refresh|Incremental Merge|Partition Replacement|
|-|-|-|-|
|Loading method|Reload all records|Insert and update changed records|Reload affected partitions|
|Processing volume|Entire dataset|Changed records|Complete affected partitions|
|New records|Supported|Supported|Supported|
|Updated records|Supported|Supported|Supported|
|Historical corrections|Complete reload|Update matching records|Replace affected partition|
|Delete handling|Missing snapshot records are removed|Requires CDC or tombstones|Removed within replaced partitions|
|Rerun safety|Supported|Supported|Supported when complete partitions are supplied|
|Suitable use case|Small or complete datasets|Small change volumes|Partitioned or date-based datasets|

## 10\. Data Quality and Traceability

Incoming records are validated before they are published to target tables.

The pipeline checks for missing or invalid values, malformed dates and timestamps, invalid IDs, unknown customers, negative amounts, invalid statuses, and duplicate or conflicting records.

Rejected records are recorded with information such as the run ID, source file, raw record, and rejection reason. This makes data quality issues easier to investigate.

## 11\. Pipeline Execution Tracking

Pipeline executions are recorded in the database.

Execution information includes:

* Run ID
* Loading strategy
* Execution status
* Input row count
* Output row count
* Rejected row count
* Execution duration
* Error details

Statuses such as `RUNNING`, `SUCCESS`, and `FAILED` help track pipeline execution and investigate failures.

## 12\. Idempotency

Idempotency means that rerunning the same input should not create duplicate records or unexpectedly change the final result.

* **Full Refresh:** Loading the same complete snapshot again produces the same target records.
* **Incremental Merge:** The business key prevents duplicate orders, while timestamp comparison prevents stale updates.
* **Partition Replacement:** Replacing the same complete affected partitions produces the same partition contents.

Idempotency is important because data pipelines may need to be restarted after failures.

## 13\. Late-Arriving Data

A record may arrive after its original order date.

For example, an order with an order date of December 31 may arrive on January 2. It still belongs to the December 31 partition.

* Full Refresh includes the late record when the complete snapshot contains it.
* Incremental Merge inserts the late record using its business key.
* Partition Replacement reloads the complete affected historical partition.

The final target tables can then be reconciled to check consistency.

## 14\. Out-of-Order Updates

An older update may arrive after a newer update for the same order.

Incremental Merge compares the incoming `updated\\\_at` timestamp with the timestamp already stored in the target. An older update must not overwrite a newer record.

This protects the target table from stale data.

## 15\. Failure Recovery and Retry

Target-table changes are performed within database transactions.

If a failure occurs before commit:

1. The transaction is rolled back.
2. Incomplete target changes are not published.
3. The failed execution can be recorded for investigation.
4. The cause can be corrected.
5. The input can be retried.

Production systems may also require immutable source snapshots, stable run IDs, checkpoints, structured logging, retry policies, and explicit CDC deletion events.

## 16\. Backfill Strategy

Backfill means reprocessing historical data to correct missing or incorrect records.

A typical backfill process is:

1. Identify the affected date range.
2. Obtain complete source data for the affected dates.
3. Identify the affected partitions.
4. Replace the affected partitions, or perform a full refresh using a complete snapshot.
5. Reconcile the final target records.
6. Review rejected records and execution logs.

Partition Replacement is useful when the correction is limited to a known set of complete partitions.

## 17\. Performance Measurement

The project measures execution time and records information such as:

* Strategy name
* Execution duration
* Input row count
* Output row count
* Rejected row count
* Final result equivalence

Benchmark results depend on the machine, database state, caching, input data, and workload. They should be treated as observations from a particular run, not universal performance guarantees.

For a fair comparison:

* Use equivalent initial conditions.
* Keep the source data consistent.
* Run multiple trials.
* Compare median execution times.
* Check final data equivalence as well as runtime.
* Report initial-load and later-batch workloads separately.

The three strategies process different amounts of data during later loads: Full Refresh receives the complete snapshot, Incremental Merge receives changed records, and Partition Replacement receives complete affected partitions. Their results should therefore be interpreted in the context of the workload.

## 18\. Automated Testing

The project uses `pytest` for automated testing.

The latest test run reported locally was:

```text
59 passed in 127.11s
```

Run the tests again in your own environment with:

```bash
python -m pytest -q
```

The test count and execution time shown above should be updated if a later test run produces a different result.

## 19\. Limitations and Future Improvements

This project is a local data engineering comparison using Python and SQLite. It is not a distributed warehouse or lakehouse performance benchmark.

Potential production improvements include:

* Distributed processing with Apache Spark or PySpark.
* Cloud data warehouses such as Snowflake or BigQuery.
* Pipeline orchestration with Apache Airflow.
* Structured logging and monitoring.
* Schema versioning.
* Source checkpoints and CDC.
* Automated data quality monitoring.
* Warehouse-specific partition management.

## 20\. Conclusion

This project demonstrates how three data loading strategies can produce equivalent final data while using different approaches to process incoming records.

* **Full Refresh** is straightforward and useful when the complete dataset can be reloaded.
* **Incremental Merge** is useful when only a small number of records change.
* **Partition Replacement** is useful when changes are limited to known partitions and complete partition data is available.

There is no single best strategy for every situation. The right choice depends on dataset size, change volume, partition design, deletion requirements, and operational needs.



