
import csv
import json
import time
import uuid

from datetime import datetime, timezone


COLUMNS = [
    "order_id",
    "order_date",
    "customer_id",
    "amount",
    "status",
    "updated_at"
]

VALID_STATUSES = {
    "PLACED",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
    "NEW",
    "PAID"
}

TARGETS = {
    "full_refresh": "full_refresh_orders",
    "incremental_merge": "incremental_orders",
    "partition_replacement": "partition_orders"
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_and_validate(path, conn, run_id):
    valid = []
    rejects = []

    with open(path, newline="", encoding="utf-8-sig") as f:

        reader = csv.DictReader(f)

        missing = set(COLUMNS) - set(reader.fieldnames or [])

        if missing:
            raise ValueError(
                "Missing columns: " + ", ".join(sorted(missing))
            )

        customer_ids = {
            r[0] for r in conn.execute(
                "SELECT customer_id FROM customers"
            )
        }

        seen = {}

        for raw in reader:

            try:
                order_id = int(raw["order_id"])
                customer_id = int(raw["customer_id"])
                amount = float(raw["amount"])

                order_date = raw["order_date"].strip()
                updated_at = raw["updated_at"].strip()
                status = raw["status"].strip()

                datetime.strptime(order_date, "%Y-%m-%d")
                datetime.fromisoformat(updated_at)

                if order_id <= 0:
                    raise ValueError("order_id must be positive")

                if customer_id not in customer_ids:
                    raise ValueError("unknown customer_id")

                if amount < 0:
                    raise ValueError("amount cannot be negative")

                if not status:
                    raise ValueError("status is required")

                if status not in VALID_STATUSES:
                    raise ValueError(
                        f"invalid order status: {status}"
                    )

                clean = (
                    order_id,
                    order_date,
                    customer_id,
                    amount,
                    status,
                    updated_at
                )

                if order_id in seen:

                    if seen[order_id] == clean:
                        continue

                    raise ValueError(
                        "conflicting duplicate order_id in input"
                    )

                seen[order_id] = clean
                valid.append(clean)

            except Exception as e:

                rejects.append(
                    (json.dumps(raw, sort_keys=True), str(e))
                )

    return valid, rejects


def _start_run(conn, strategy, path):

    run_id = str(uuid.uuid4())

    conn.execute("""
        INSERT INTO pipeline_runs
        (run_id, strategy, started_at, status)
        VALUES (?, ?, ?, 'RUNNING')
    """, (run_id, strategy, now()))

    conn.commit()

    return run_id


def _finish(
    conn,
    run_id,
    status,
    input_count,
    output_count,
    rejected_count,
    duration,
    error=None
):

    conn.execute("""
        UPDATE pipeline_runs
        SET ended_at=?,
            status=?,
            input_count=?,
            output_count=?,
            rejected_count=?,
            duration_ms=?,
            error_message=?
        WHERE run_id=?
    """, (
        now(),
        status,
        input_count,
        output_count,
        rejected_count,
        duration,
        error,
        run_id
    ))

    conn.commit()


def run_strategy(
    conn,
    strategy,
    source_file,
    changed_partitions=None,
    fail_before_commit=False
):

    if strategy not in TARGETS:
        raise ValueError(f"Unknown strategy: {strategy}")

    target = TARGETS[strategy]

    run_id = _start_run(conn, strategy, source_file)

    started = time.perf_counter()

    input_count = 0
    output_count = 0
    rejected_count = 0

    try:

        valid, rejects = read_and_validate(
            source_file,
            conn,
            run_id
        )

        input_count = len(valid) + len(rejects)
        rejected_count = len(rejects)

        conn.execute("BEGIN")

        for raw, reason in rejects:

            conn.execute("""
                INSERT INTO rejects
                (run_id, source_file, raw_record, reason)
                VALUES (?, ?, ?, ?)
            """, (
                run_id,
                str(source_file),
                raw,
                reason
            ))

        # FULL REFRESH

        if strategy == "full_refresh":

            conn.execute(f"DELETE FROM {target}")

            conn.executemany(
                f"INSERT INTO {target} VALUES (?, ?, ?, ?, ?, ?)",
                valid
            )

        # INCREMENTAL MERGE

        elif strategy == "incremental_merge":

            conn.executemany(f"""
                INSERT INTO {target}
                VALUES (?, ?, ?, ?, ?, ?)

                ON CONFLICT(order_id)
                DO UPDATE SET

                    order_date = excluded.order_date,
                    customer_id = excluded.customer_id,
                    amount = excluded.amount,
                    status = excluded.status,
                    updated_at = excluded.updated_at

                WHERE excluded.updated_at >= {target}.updated_at
            """, valid)

        # PARTITION REPLACEMENT

        elif strategy == "partition_replacement":

            # Source must contain COMPLETE contents
            # of each listed date partition.

            partitions = sorted(
                set(
                    changed_partitions
                    or [r[1] for r in valid]
                )
            )

            for partition in partitions:

                conn.execute(
                    f"DELETE FROM {target} WHERE order_date=?",
                    (partition,)
                )

                partition_rows = [
                    r for r in valid
                    if r[1] == partition
                ]

                conn.executemany(
                    f"INSERT INTO {target} VALUES (?, ?, ?, ?, ?, ?)",
                    partition_rows
                )

        if fail_before_commit:
            raise RuntimeError(
                "Simulated failure before commit"
            )

        output_count = conn.execute(
            f"SELECT COUNT(*) FROM {target}"
        ).fetchone()[0]

        conn.commit()

        duration = (
            time.perf_counter() - started
        ) * 1000

        _finish(
            conn,
            run_id,
            "SUCCESS",
            input_count,
            output_count,
            rejected_count,
            duration
        )

        return {
            "run_id": run_id,
            "strategy": strategy,
            "status": "SUCCESS",
            "input_count": input_count,
            "output_count": output_count,
            "rejected_count": rejected_count,
            "duration_ms": round(duration, 3)
        }

    except Exception as e:

        conn.rollback()

        duration = (
            time.perf_counter() - started
        ) * 1000

        _finish(
            conn,
            run_id,
            "FAILED",
            input_count,
            0,
            rejected_count,
            duration,
            str(e)
        )

        return {
            "run_id": run_id,
            "strategy": strategy,
            "status": "FAILED",
            "input_count": input_count,
            "output_count": 0,
            "rejected_count": rejected_count,
            "duration_ms": round(duration, 3),
            "error": str(e)
        }


def snapshot(conn, table):

    return [
        tuple(row)
        for row in conn.execute(f"""
            SELECT
                order_id,
                order_date,
                customer_id,
                amount,
                status,
                updated_at
            FROM {table}
            ORDER BY order_id
        """)
    ]

