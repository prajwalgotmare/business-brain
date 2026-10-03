import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from business_brain.data import DocumentManifest, GroundTruthManifest

ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> DocumentManifest:
    return DocumentManifest.model_validate_json(
        (ROOT / "data/documents/document_manifest.json").read_text()
    )


def test_document_manifest_schema_and_corpus_are_complete() -> None:
    manifest = _manifest()
    schema = json.loads((ROOT / "data/schemas/document_manifest.schema.json").read_text())
    assert schema["title"] == "DocumentManifest"
    assert manifest.document_count == 12
    assert manifest.synthetic_count == 10
    assert manifest.public_reference_count == 2
    assert sum(item.ingest for item in manifest.documents) == 10


def test_pdf_hashes_pages_and_text_match_manifest() -> None:
    for document in _manifest().documents:
        path = ROOT / document.relative_path
        content = path.read_bytes()
        reader = PdfReader(path)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        assert len(content) == document.byte_count
        assert hashlib.sha256(content).hexdigest() == document.sha256
        assert len(reader.pages) == document.page_count
        assert len(text.strip()) >= 100


def test_scenario_document_dependencies_resolve_to_available_clauses() -> None:
    documents = {item.document_id: item for item in _manifest().documents}
    scenarios = GroundTruthManifest.model_validate_json(
        (ROOT / "data/evaluation/ground_truth_scenarios.json").read_text()
    )
    for scenario in scenarios.scenarios:
        for dependency in scenario.document_dependencies:
            assert dependency.status == "available"
            assert dependency.document_id in documents
            assert dependency.clause_id in documents[dependency.document_id].clause_ids


def test_scenario_clauses_and_values_are_extractable() -> None:
    expected_text = {
        "doc_aur_packaging_agreement.pdf": (
            "clause_price_tier_3_1",
            "USD 0.42",
            "Net 60",
        ),
        "doc_aur_skincare_agreement.pdf": (
            "clause_late_payment_6_3",
            "1.5 percent per month",
        ),
        "doc_aur_fedex_msa.pdf": (
            "clause_sla_credit_4_2",
            "Credit rate: 10%",
        ),
        "doc_aur_invoice_inv_00010.pdf": ("USD 4,108.68", "USD 61.63"),
        "doc_aur_invoice_frt_00034.pdf": ("shp_aur_000021", "USD 18.00"),
    }
    for filename, required in expected_text.items():
        path = ROOT / "data/documents/aura_brands" / filename
        text = "".join(page.extract_text() or "" for page in PdfReader(path).pages)
        assert all(value in text for value in required)
