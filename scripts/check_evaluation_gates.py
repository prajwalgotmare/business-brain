"""Fail CI when the committed evaluation report regresses below locked floors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "data" / "evaluation" / "latest_evaluation_run.json"
DEFAULT_POLICY = ROOT / "data" / "quality" / "evaluation_gate_policy.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_gates(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    metrics = report.get("metrics", {})
    failures: list[str] = []
    checks = {
        "case_count": (metrics.get("case_count"), policy["dataset_case_count"], "=="),
        "ragas_case_count": (
            metrics.get("ragas_case_count"),
            policy["minimum_ragas_cases"],
            ">=",
        ),
        "ragas_groundedness": (
            metrics.get("ragas_groundedness"),
            policy["minimum_ragas_groundedness"],
            ">=",
        ),
        "citation_recall": (
            metrics.get("citation_recall"),
            policy["minimum_citation_recall"],
            ">=",
        ),
        "routing_accuracy": (
            metrics.get("routing_accuracy"),
            policy["minimum_routing_accuracy"],
            ">=",
        ),
        "permission_accuracy": (
            metrics.get("permission_accuracy"),
            policy["minimum_permission_accuracy"],
            ">=",
        ),
        "action_policy_accuracy": (
            metrics.get("action_policy_accuracy"),
            policy["minimum_action_policy_accuracy"],
            ">=",
        ),
        "task_success_rate": (
            metrics.get("task_success_rate"),
            policy["minimum_task_success_rate"],
            ">=",
        ),
        "runtime_error_count": (
            metrics.get("runtime_error_count"),
            policy["maximum_runtime_errors"],
            "<=",
        ),
    }
    for name, (actual, expected, operator) in checks.items():
        passed = (
            actual == expected
            if operator == "=="
            else actual >= expected
            if operator == ">="
            else actual <= expected
        )
        if not passed:
            failures.append(f"{name}: actual={actual!r}, required {operator} {expected!r}")
    if report.get("dataset_version") != "1.0":
        failures.append(f"dataset_version: unsupported {report.get('dataset_version')!r}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    failures = evaluate_gates(load_json(args.report), load_json(args.policy))
    if failures:
        print("Evaluation gates FAILED:")
        print("\n".join(f"- {failure}" for failure in failures))
        raise SystemExit(1)
    print("Evaluation gates PASSED")


if __name__ == "__main__":
    main()
