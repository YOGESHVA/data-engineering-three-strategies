# Reviewer Corrections — Implementation and Verification

This document maps the supplied C01–C15 review to the changes in this delivery. The review's terminology and acceptance criteria are retained. Test evidence is from the clean project tree in this archive.

## Correction status

| ID | Status | Implementation in this delivery |
|---|---|---|
| C01 | Complete | Manual script renamed and guarded; `pytest.ini` limits discovery to `tests`; tests use temporary databases. |
| C02 | Complete | Timezone-aware ISO timestamps normalized to fixed-width UTC microseconds; stale versions ignored; identical equal-version payloads are no-ops; conflicting equal-version payloads fail. |
| C03 | Complete for supplied benchmark workloads | Failed runs, rejects, mismatches and independent-oracle mismatches fail comparison/CLI; initial-load and later-batch reports use expected-state snapshots. |
| C04 | Partial | Strict CSV parsing, exact header schema, duplicate-header rejection, short/extra row checks, invalid encoding failure, canonical dates, finite bounded Decimal validation and explicit rejects. Monetary totals are reconciled in integer cents, but SQLite target storage remains `REAL`; see design limitation below. |
| C05 | Complete | Physical source records, accepted unique rows, exact duplicates, rejects, stale/unchanged rows, inserts/updates/deletes, ignored scope and target-after counts are persisted. |
| C06 | Partial | `None` derives scope; `[]` means no-op; explicit empty partition deletes; moved keys require old and new dates; replacement with rejects aborts; scenario generator supplies complete affected partitions and a manifest. Runtime callers remain responsible for supplying complete snapshots; the loader cannot independently prove source completeness. |
| C07 | Complete for tested transaction boundaries | Reject evidence is committed separately before target mutation; failures roll back populated targets; target publication and terminal SUCCESS status share one transaction; retry tests cover all strategies. |
| C08 | Complete on fresh databases | All three targets enforce customer foreign keys, non-null fields, amount checks and status checks; rejects reference pipeline runs; executable SQL DDL and data dictionary are included. Existing legacy DBs should be rebuilt to gain constraints not retrofitted by SQLite. |
| C09 | Complete for row-level load lineage | Each attempt records source path, SHA-256, mode and partition scope; rejects retain source record numbers; all strategies write INSERT/DELETE history and merge writes UPDATE history with old/new values. |
| C10 | Complete for the supported synthetic scenarios | Separate later-batch benchmark compares full final snapshot, incremental delta and complete affected partitions from identical base states; repeated trials, alternating strategy order, medians and independent expected final state are reported. |
| C11 | Complete | Existing benchmark DB paths are protected unless `--reset` is explicitly supplied; report paths are configurable; default trials use temporary DBs. |
| C12 | Complete for included deterministic scenarios | Clean base/delta/partition datasets, expected final state, manifest, anomaly feed and separate labels are generated from a local seeded RNG. |
| C13 | Expanded regression coverage | 59 automated tests cover the original suite plus timestamp, malformed CSV, accounting, partition, FK, lineage, benchmark, failure/retry, empty-batch and generated-scenario cases. |
| C14 | Complete | README Markdown and commands cleaned; clone/setup instructions, Linux/macOS and Windows activation guidance, benchmark commands and field dictionary included. |
| C15 | Complete for delivery archive | Duplicate task scripts are avoided; no nested ZIP, database or Git metadata is shipped; synthetic source manifest and structured JSON operational events are included. |

## Verification performed

- `python -m pytest -q` — 59 passed.
- `python -m compileall -q src tests` — passed.
- `python -m src.demo` — all three targets equivalent on the demo's supported scenario.
- `python -m src.benchmark --input data/generated/orders.csv --trials 3 --report reports/strategy_comparison.json` — independent expected-state comparison passed.
- `python -m src.later_batch_benchmark --output data/scenario --base-rows 1000 --updates 50 --inserts 50 --seed 42 --trials 3 --report reports/later_batch_comparison.json` — all strategies matched the independent expected final state.
- `PRAGMA foreign_key_check` — covered by automated test.

## Explicit design limitation

Amounts are validated with `Decimal`, restricted to two fractional digits and a bounded range. Benchmark reconciliation converts values to integer cents before comparing monetary aggregates. The public target schema nevertheless retains SQLite `REAL` for compatibility with the original project. For exact persisted monetary arithmetic, migrate target storage to integer cents with a versioned schema migration before using real monetary data. Partition completeness is a caller contract: the included scenario generator emits a manifest and complete affected-partition files, but the loader does not independently prove that a caller supplied every row in a partition. This is a synthetic SQLite teaching project, not a production financial ledger.
