import json
from pathlib import Path

from business_brain.experiments.tracking import build_experiment_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_experiment_manifest_hashes_artifacts() -> None:
    artifact = ROOT / "data/quality/stockout_forecast_metrics.json"
    manifest = build_experiment_manifest(
        run_name="test-run",
        parameters={"seed": 42},
        metrics={"mae": 1.0},
        artifacts=[artifact],
    )

    assert manifest["tracker"]["name"] == "DagsHub"
    assert manifest["artifacts"][0]["sha256"]


def test_performance_artifact_has_required_measurements() -> None:
    report = json.loads(
        (ROOT / "data/quality/performance_benchmark.json").read_text(encoding="utf-8")
    )

    assert report["forecast_training_latency_ms"]["p95"] >= 0
    assert report["latest_agent_run"]["total_tokens"] > 0
