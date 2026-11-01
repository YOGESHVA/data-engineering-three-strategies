# Design and Trade-off Note

## Chosen dataset
Orders at one-row-per-order grain. `order_id` is the stable business key. `order_date` is the partition column. `customer_id` references customers.

## Correctness
All three strategies are compared using sorted target rows with identical columns. A passing equivalence assertion means the resulting current-state snapshots match for the tested source snapshot.

## Complexity
- Full refresh: simplest implementation and simplest mental model.
- Incremental merge: moderate complexity; requires stable keys and change detection.
- Partition replacement: moderate complexity; requires identifying affected partitions and obtaining complete partition contents.

## Failure recovery
- Full refresh: transaction rollback keeps the old target if the load fails before commit; otherwise rerun the full snapshot.
- Incremental merge: transaction rollback protects partial writes; idempotent upsert makes retry safe.
- Partition replacement: transaction rollback restores the prior partitions if replacement fails; retry the same complete partition snapshots.

## Performance
Record measured wall-clock duration, input rows, output rows, and rejects. Full refresh usually performs more writes. Merge is attractive for small deltas. Partition replacement can be efficient when few partitions change but each changed partition is substantial.

## Optimization
Add indexes on business key and partition key. In a warehouse, use native partition pruning and bulk/staging-table operations rather than row-at-a-time writes.

## Caveat
A fair comparison must use the same logical final source state and correct inputs for each strategy. Partition replacement must receive full data for affected partitions; merge must receive all relevant changes, including deletes if the source supports them.
