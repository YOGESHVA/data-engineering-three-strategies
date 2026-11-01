# Design and Trade-off Analysis

## 1. Dataset and target grain

The project models an orders dataset with one row per current order.

| Attribute | Definition |
|---|---|
| Business key | `order_id` |
| Partition column | `order_date` |
| Customer reference | `customer_id` |
| Measure | `amount` |
| Version field | `updated_at` |

The three strategies publish to independent targets: `full_refresh_orders`, `incremental_orders`, and `partition_orders`. All comparisons use the same six business columns, ordered by `order_id`.

## 2. Input contracts

- Full refresh requires a complete current-state snapshot.
- Incremental merge requires the relevant inserts and changed records. It uses `order_id` as the key and a timezone-aware `updated_at` version.
- Partition replacement requires complete contents for every date in the supplied partition scope. `None` derives the dates from the input; `[]` means no partitions. Moving an order between dates requires both old and new dates in scope.
- CDC deletes are not implemented by incremental merge. Do not infer delete support from the other two snapshot strategies.

## 3. Strategy complexity and trade-offs

### Full refresh

**Work:** delete the current target and insert the complete input snapshot. The dominant data work is approximately O(N) for N source rows.

**Advantages:** simple semantics, easy reconciliation, and missing source records are removed naturally when the input is a complete snapshot.

**Trade-offs:** unchanged rows are rewritten, the full dataset must be available, and the write cost grows with total data size.

### Incremental merge

**Work:** perform a primary-key lookup for each of D changed rows, then insert or update when the incoming version is newer. With an indexed key this is approximately O(D log N) database lookup work, excluding validation and customer-reference checks.

**Advantages:** avoids rewriting unchanged records and is effective when D is much smaller than N.

**Trade-offs:** depends on stable business keys, correct version timestamps, and a trustworthy change feed. Older updates are counted as stale; equal-version identical rows are no-ops; equal-version conflicting payloads fail. CDC deletes require tombstones or another explicit mechanism.

### Partition replacement

**Work:** group the input rows by date once, delete each affected target partition, then insert the complete replacement rows. Python grouping is O(A) for A input rows, plus per-partition database work.

**Advantages:** unaffected partitions remain untouched; useful for historical corrections and late-arriving records when only a small number of dates change.

**Trade-offs:** every affected partition must be complete. A partial delta must never be passed as a complete replacement snapshot. Large or numerous affected partitions reduce the advantage. The loader validates the declared scope and movement rules, but completeness remains a caller contract supported by the generated scenario manifest.

## 4. Correctness and reconciliation

Validation includes positive order IDs, known customer references, canonical dates, timezone-aware timestamps, finite non-negative amounts with at most two decimal places, and an allowed status. CSV schema and row width are checked explicitly.

The physical source accounting equation is:

`source_records = accepted_unique + exact_duplicates + rejected_records`

For target cardinality:

`target_after = target_before + inserts - deletes`

Updates do not change cardinality. Benchmarks compare each target with an independently constructed expected snapshot, check key sets and row counts, and reconcile amount totals in integer cents. The SQLite target column remains `REAL` for compatibility; see the monetary storage limitation below.

## 5. Failure recovery, rejects, and lineage

Target writes are transactional. Injected pre-commit failures roll back target changes, and tests cover populated targets for all three strategies. Known reject evidence is committed separately so it survives target rollback. Target publication and terminal `SUCCESS` status are committed in the same transaction.

Each attempt records a run ID, source path, source SHA-256, input mode and partition scope. Rejects retain physical source-record numbers. Change history records insert/delete events for all strategies and old/new values for merge updates. Structured JSON run events include the run ID, strategy, counts and failure information.

## 6. Benchmark interpretation

The initial-load benchmark measures the same 100,000-row snapshot for each strategy. The later-batch benchmark starts from identical base states and compares:

- Full refresh: complete final snapshot.
- Incremental merge: updates plus inserts only.
- Partition replacement: complete contents of affected dates.

Trials rotate strategy order and report median durations. These are local SQLite measurements, not distributed or lakehouse performance claims. Generator, file preparation and report serialization are outside the measured strategy call.

## 7. Supported edge cases and limits

The tests cover late arrivals, out-of-order updates, exact/conflicting duplicates, malformed CSV, missing/extra fields, invalid encodings, timezone offsets, fractional timestamps, equal-version conflicts, empty batches, partition movement, reject preservation, rollback/retry, database constraints and benchmark failure gating.

**Monetary storage limitation:** amounts are parsed and validated with `Decimal`, and benchmark totals are reconciled in integer cents. The public target schema retains SQLite `REAL` to preserve compatibility with the original project. For exact persisted financial arithmetic, migrate target storage to integer cents with a versioned schema migration before using real financial data.

**Partition completeness limitation:** the included generator writes a manifest and complete affected-partition input. The loader cannot independently prove that an arbitrary caller supplied every row in a partition; that guarantee remains part of the input contract.

This is a synthetic SQLite learning prototype, not a production financial ledger or a claim of distributed-scale performance.
