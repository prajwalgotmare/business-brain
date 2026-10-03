import hashlib
import json
from pathlib import Path

from business_brain.data import DataQualityManifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data/quality/data_quality_manifest.json"


def _manifest() -> DataQualityManifest:
    return DataQualityManifest.model_validate_json(MANIFEST_PATH.read_text())


def test_quality_manifest_and_schema_are_committed_and_valid() -> None:
    manifest = _manifest()
    schema = json.loads(
        (ROOT / "data/schemas/data_quality_manifest.schema.json").read_text()
    )
    assert manifest.status == "pass"
    assert schema["title"] == "DataQualityManifest"
    assert {check.check_id for check in manifest.checks} == {
        "artifacts_current",
        "row_counts",
        "primary_keys",
        "tenant_isolation",
        "schema_validation",
        "totals_reconcile",
        "inventory_reconciles",
        "dates_valid",
        "scenario_evidence",
    }


def test_every_fingerprint_matches_the_committed_artifact() -> None:
    manifest = _manifest()
    for artifact in manifest.artifacts:
        content = (ROOT / artifact.relative_path).read_bytes()
        assert len(content) == artifact.byte_count
        assert hashlib.sha256(content).hexdigest() == artifact.sha256


def test_csv_fingerprints_cover_both_isolated_tenants() -> None:
    manifest = _manifest()
    csv_artifacts = [
        artifact for artifact in manifest.artifacts if artifact.media_type == "text/csv"
    ]
    assert manifest.csv_file_count == 34
    assert {artifact.tenant_id for artifact in csv_artifacts} == {
        "tenant_aura",
        "tenant_apex",
    }
    assert all((artifact.row_count or 0) > 0 for artifact in csv_artifacts)

