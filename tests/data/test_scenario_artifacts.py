import json
from pathlib import Path

from business_brain.data.scenario_models import GroundTruthManifest

ROOT = Path(__file__).resolve().parents[2]


def test_scenario_manifest_and_schema_are_committed_and_valid() -> None:
    manifest_payload = json.loads(
        (ROOT / "data/evaluation/ground_truth_scenarios.json").read_text()
    )
    schema = json.loads(
        (ROOT / "data/schemas/scenario_ground_truth.schema.json").read_text()
    )
    manifest = GroundTruthManifest.model_validate(manifest_payload)
    assert len(manifest.scenarios) == 6
    assert schema["title"] == "GroundTruthManifest"


def test_manifest_evidence_never_references_apex_records() -> None:
    payload = json.loads(
        (ROOT / "data/evaluation/ground_truth_scenarios.json").read_text()
    )
    record_ids = [
        evidence["record_id"]
        for scenario in payload["scenarios"]
        for evidence in scenario["evidence"]
    ]
    assert not any("apx" in record_id for record_id in record_ids)
