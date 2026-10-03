"""Run the bounded Business Brain golden evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_brain.evaluation.runner import (
    load_golden_manifest,
    run_sync,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "data" / "evaluation" / "golden_dataset.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "evaluation" / "latest_evaluation_run.json",
    )
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=None)
    parser.add_argument("--skip-ragas", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--case-delay", type=float, default=0)
    parser.add_argument("--ragas-delay", type=float, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_golden_manifest(args.dataset)
    report = run_sync(
        manifest,
        case_limit=args.case_limit,
        case_ids=set(args.case_id) if args.case_id else None,
        enable_ragas=not args.skip_ragas,
        max_tokens=args.max_tokens,
        case_delay_seconds=args.case_delay,
        ragas_delay_seconds=args.ragas_delay,
    )
    write_report(report, args.output)
    print(json.dumps(report.metrics.model_dump(mode="json"), indent=2))
    if not all(report.threshold_results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
