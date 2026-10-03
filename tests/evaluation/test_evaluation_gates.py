import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.check_evaluation_gates import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]


def report_and_policy() -> tuple[dict, dict]:
    report = json.loads(
        (ROOT / "data" / "evaluation" / "latest_evaluation_run.json").read_text(
            encoding="utf-8"
        )
    )
    policy = json.loads(
        (ROOT / "data" / "quality" / "evaluation_gate_policy.json").read_text(
            encoding="utf-8"
        )
    )
    return report, policy


def test_gate_policy_passes_the_committed_baseline() -> None:
    report, policy = report_and_policy()
    assert evaluate_gates(report, policy) == []


def test_gate_policy_detects_quality_regression() -> None:
    report, policy = report_and_policy()
    regressed = copy.deepcopy(report)
    regressed["metrics"]["ragas_groundedness"] = 0.2
    regressed["metrics"]["task_success_rate"] = 0.1

    failures = evaluate_gates(regressed, policy)

    assert any("ragas_groundedness" in failure for failure in failures)
    assert any("task_success_rate" in failure for failure in failures)


def test_gate_policy_requires_the_complete_dataset() -> None:
    report, policy = report_and_policy()
    report["metrics"]["case_count"] = 49

    failures = evaluate_gates(report, policy)

    assert any("case_count" in failure for failure in failures)
