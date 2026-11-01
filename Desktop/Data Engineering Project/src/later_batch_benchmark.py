
"""Benchmark realistic later-batch inputs against an independent expected snapshot."""

import argparse
import csv
import json
import statistics
import sys
import tempfile
import time
import platform
from decimal import Decimal
from pathlib import Path

from src.db import connect, seed_customers
from src.strategies import run_strategy, snapshot
from src.scenario_generator import generate_scenario


CONFIG = [
    ('full_refresh', 'full_refresh_final.csv', 'full_refresh_orders'),
    ('incremental_merge', 'incremental_delta.csv', 'incremental_orders'),
    ('partition_replacement', 'partition_complete_affected.csv', 'partition_orders')
]


def _rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def run(
    output_dir='data/scenario',
    base_rows=1000,
    updates=50,
    inserts=50,
    seed=42,
    trials=3,
    report='reports/later_batch_comparison.json'
):
    if trials < 1:
        raise ValueError('trials must be >= 1')

    manifest = generate_scenario(
        output_dir, base_rows, updates, inserts, seed
    )

    root = Path(output_dir)
    expected = []

    for r in _rows(root / 'expected_final.csv'):
        expected.append((
            int(r['order_id']),
            r['order_date'],
            int(r['customer_id']),
            float(r['amount']),
            r['status'],
            r['updated_at'].replace('+00:00', 'Z')
        ))

    expected.sort(key=lambda x: x[0])
    expected_keys = {r[0] for r in expected}
    expected_cents = sum(
        int(Decimal(str(r[3])) * 100) for r in expected
    )

    trial_data = []

    for n in range(trials):
        run_results = {}
        times = {}
        states = {}

        ordered = CONFIG[n % len(CONFIG):] + CONFIG[:n % len(CONFIG)]

        for strategy, filename, target in ordered:

            # Create a temporary directory instead of an open temporary file.
            # This avoids the Windows SQLite file-locking problem.
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / 'benchmark.db'
                c = connect(str(db_path))

                try:
                    seed_customers(
                        c,
                        [(i, f'Customer {i}') for i in range(1, 101)]
                    )

                    base = run_strategy(
                        c, strategy, str(root / 'base.csv')
                    )

                    if base['status'] != 'SUCCESS':
                        raise RuntimeError(
                            f'{strategy} base load failed: {base}'
                        )

                    parts = (
                        manifest['affected_partitions']
                        if strategy == 'partition_replacement'
                        else None
                    )

                    start = time.perf_counter()

                    result = run_strategy(
                        c,
                        strategy,
                        str(root / filename),
                        changed_partitions=parts
                    )

                    times[strategy] = (
                        time.perf_counter() - start
                    ) * 1000

                    run_results[strategy] = result
                    states[strategy] = snapshot(c, target)

                finally:
                    c.close()

        oracle = {
            s: states[s] == expected
            for s, _, _ in CONFIG
        }

        checks = {}

        for s, _, _ in CONFIG:
            state = states[s]
            actual_cents = sum(
                int(Decimal(str(r[3])) * 100) for r in state
            )

            checks[s] = {
                'row_count': len(state),
                'key_set_match': {r[0] for r in state} == expected_keys,
                'amount_total_cents': actual_cents,
                'amount_total_cents_match': actual_cents == expected_cents
            }

        success = all(
            r['status'] == 'SUCCESS'
            and r.get('rejected_count', 0) == 0
            for r in run_results.values()
        )

        trial_data.append({
            'trial': n + 1,
            'execution_success': success,
            'oracle_match': oracle,
            'oracle_checks': checks,
            'comparison_passed': (
                success
                and all(oracle)
                and all(
                    v['key_set_match']
                    and v['amount_total_cents_match']
                    for v in checks.values()
                )
            ),
            'duration_ms': times,
            'results': run_results
        })

    medians = {
        s: round(
            statistics.median(
                t['duration_ms'][s] for t in trial_data
            ),
            3
        )
        for s, _, _ in CONFIG
    }

    report_data = {
        'workload': (
            'later batch: full final snapshot vs incremental delta '
            'vs complete affected partitions'
        ),
        'environment': {
            'python': sys.version.split()[0],
            'platform': platform.platform()
        },
        'manifest': manifest,
        'trials': trials,
        'trial_order': 'rotated/alternated by trial',
        'expected_amount_total_cents': expected_cents,
        'median_duration_ms': medians,
        'comparison_passed': all(
            t['comparison_passed'] for t in trial_data
        ),
        'trial_results': trial_data
    }

    p = Path(report)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report_data, indent=2), encoding='utf-8')

    print(json.dumps(report_data, indent=2))
    return report_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--output', default='data/scenario')
    parser.add_argument('--base-rows', type=int, default=1000)
    parser.add_argument('--updates', type=int, default=50)
    parser.add_argument('--inserts', type=int, default=50)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument(
        '--report',
        default='reports/later_batch_comparison.json'
    )

    args = parser.parse_args()

    try:
        result = run(
            args.output,
            args.base_rows,
            args.updates,
            args.inserts,
            args.seed,
            args.trials,
            args.report
        )

        sys.exit(0 if result['comparison_passed'] else 1)

    except Exception as e:
        print(
            f'Later-batch benchmark failed: {e}',
            file=sys.stderr
        )
        sys.exit(1)
