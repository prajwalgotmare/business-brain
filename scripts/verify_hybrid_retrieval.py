"""Run reproducible live retrieval, citation, and isolation smoke checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from business_brain.core.config import Settings
from business_brain.retrieval.hybrid import HybridRetriever
from business_brain.security.context import AuthContext, UserRole

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "quality" / "hybrid_retrieval_smoke.json"

CASES = (
    (
        "carrier_sla_credit",
        "late delivery credit rate under the carrier SLA",
        UserRole.STAFF_ACCOUNTANT,
        "doc_aur_fedex_msa",
        "clause_sla_credit_4_2",
    ),
    (
        "packaging_price",
        "contracted wholesale unit price USD 0.42 for 10,000 through 24,999 units",
        UserRole.FOUNDER_CFO,
        "doc_aur_packaging_agreement",
        "clause_price_tier_3_1",
    ),
    (
        "packaging_payment_terms",
        "Net 60 invoice payment terms for packaging supplier",
        UserRole.FOUNDER_CFO,
        "doc_aur_packaging_agreement",
        "clause_payment_terms_5_2",
    ),
    (
        "late_payment_charge",
        "late payment charge for an overdue supplier balance",
        UserRole.STAFF_ACCOUNTANT,
        "doc_aur_skincare_agreement",
        "clause_late_payment_6_3",
    ),
    (
        "support_return_policy",
        "customer return policy and shipping delay advisory",
        UserRole.SUPPORT_INTERN,
        "doc_aur_return_shipping_policy",
        None,
    ),
)


def main() -> None:
    retriever = HybridRetriever(settings=Settings())
    results = []
    for case_id, query, role, document_id, clause_id in CASES:
        started = perf_counter()
        result = retriever.search(
            query,
            AuthContext(tenant_id="tenant_aura", user_id="retrieval-smoke", role=role),
            limit=5,
        )
        latency_ms = round((perf_counter() - started) * 1_000, 2)
        expected_rank = next(
            (
                rank
                for rank, hit in enumerate(result.hits, start=1)
                if hit.citation.document_id == document_id
                and (clause_id is None or hit.citation.clause_id == clause_id)
            ),
            None,
        )
        if expected_rank is None:
            raise RuntimeError(f"Expected citation missing for {case_id}")
        results.append(
            {
                "case_id": case_id,
                "role": role.value,
                "expected_document_id": document_id,
                "expected_clause_id": clause_id,
                "expected_rank": expected_rank,
                "latency_ms": latency_ms,
            }
        )

    blocked = retriever.search(
        "packaging wholesale price and commercial terms",
        AuthContext(
            tenant_id="tenant_aura",
            user_id="retrieval-smoke",
            role=UserRole.SUPPORT_INTERN,
        ),
        limit=5,
    )
    if any(hit.citation.document_id == "doc_aur_packaging_agreement" for hit in blocked.hits):
        raise RuntimeError("Support role retrieved executive packaging agreement")

    adversarial = retriever.search(
        "supplier prices and carrier agreements",
        AuthContext(
            tenant_id="tenant_apex",
            user_id="retrieval-smoke",
            role=UserRole.FOUNDER_CFO,
        ),
        limit=5,
    )
    if adversarial.hits:
        raise RuntimeError("Apex tenant retrieved Aura documents")

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "collection_name": retriever.settings.qdrant_collection,
        "fusion": "rrf",
        "reranker": "identifier_aware_deterministic_v1",
        "case_count": len(results),
        "cases": results,
        "support_executive_leak_count": 0,
        "cross_tenant_leak_count": 0,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified retrieval cases: {len(results)}")
    print("Support executive leaks: 0")
    print("Cross-tenant leaks: 0")


if __name__ == "__main__":
    main()
