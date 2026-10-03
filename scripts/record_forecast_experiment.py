"""Record the verified forecast run as a DagsHub-compatible local manifest."""

from __future__ import annotations

import json
from pathlib import Path

from business_brain.experiments.tracking import build_experiment_manifest, write_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    metrics_path = ROOT / "data/quality/stockout_forecast_metrics.json"
    model_path = ROOT / "data/quality/stockout_xgboost.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    manifest = build_experiment_manifest(
        run_name="aura-stockout-xgboost-v1",
        parameters={
            "model": metrics["model"],
            "features": metrics["feature_names"],
            "split": metrics["split"],
            "random_seed": 42,
        },
        metrics=metrics["metrics"],
        artifacts=[metrics_path, model_path],
    )
    output = ROOT / "data/experiments/forecast_run.json"
    write_manifest(manifest, output)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
