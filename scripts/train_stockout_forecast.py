"""Train and evaluate the leakage-safe stockout demand model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_brain.forecasting.stockout import build_dataset, train_and_evaluate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-dir", type=Path, default=ROOT / "data/generated/aura_brands")
    parser.add_argument(
        "--model", type=Path, default=ROOT / "data/quality/stockout_xgboost.json"
    )
    parser.add_argument(
        "--metrics", type=Path, default=ROOT / "data/quality/stockout_forecast_metrics.json"
    )
    args = parser.parse_args()
    dataset = build_dataset(args.tenant_dir / "orders.csv", args.tenant_dir / "order_lines.csv")
    metrics = train_and_evaluate(dataset, args.model)
    payload = {
        "model": "xgboost",
        "feature_names": ["lag_1", "lag_2", "rolling_3", "week_index"],
        "split": {"strategy": "time_ordered", "cutoff_week": dataset.cutoff_week.isoformat()},
        "metrics": metrics.__dict__,
    }
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
