"""Measure local forecast latency and summarize the latest LLM evaluation run."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from business_brain.forecasting.stockout import build_dataset, train_and_evaluate

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 3)


def main() -> None:
    tenant = ROOT / "data/generated/aura_brands"
    dataset = build_dataset(tenant / "orders.csv", tenant / "order_lines.csv")
    latencies: list[float] = []
    for _ in range(10):
        started = time.perf_counter()
        train_and_evaluate(dataset)
        latencies.append((time.perf_counter() - started) * 1_000)
    evaluation = json.loads(
        (ROOT / "data/evaluation/latest_evaluation_run.json").read_text(encoding="utf-8")
    )["metrics"]
    report = {
        "schema_version": "1.0",
        "forecast_training_latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "mean": round(statistics.mean(latencies), 3),
            "samples": len(latencies),
        },
        "latest_agent_run": {
            "case_count": evaluation["case_count"],
            "mean_latency_ms": evaluation["mean_latency_ms"],
            "total_tokens": evaluation["total_tokens"],
            "fallback_case_count": evaluation["fallback_case_count"],
        },
        "cost_note": (
            "LLM prices are intentionally not hardcoded; use the provider dashboard "
            "for current billing."
        ),
    }
    output = ROOT / "data/quality/performance_benchmark.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
