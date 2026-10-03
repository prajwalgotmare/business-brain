# Golden Evaluation Dataset

Version: 1.0  
Verified: 2026-10-03

The golden set is a deterministic, machine-readable collection of 50 questions for the
Aura Brands tenant. It is stored in `data/evaluation/golden_dataset.json`; its strict JSON
Schema is stored in `data/schemas/golden_evaluation.schema.json`.

## Coverage

| Category | Cases | What is evaluated |
| --- | ---: | --- |
| Fixed SQL analytics | 16 | Stockout, freight reconciliation, overdue invoices, margin variance |
| Cited document retrieval | 10 | Carrier SLA, supplier price/payment clauses, late charge, public returns |
| Approval-gated action drafting | 8 | PO, carrier dispute, payment reminder, delay advisory |
| Authorization refusal | 12 | Role boundaries, forbidden finance/actions, cross-tenant request |
| Direct response | 2 | Safe general conversation routing |
| Unsupported operation | 2 | Destructive database and real-money transfer refusal |

All four roles are represented: 21 Founder/CFO, 8 Logistics Manager, 10 Staff Accountant,
and 11 Support Intern cases.

## Expected outputs

Every case records:

- authenticated tenant and role;
- expected route, intent, workflow status, tool, and safe error code;
- exact expected business facts and a concise reference summary;
- document, page, and clause expectations where citations are required;
- required and forbidden answer strings for deterministic checks;
- action risk, approver roles, approval requirement, and submission prohibition;
- source scenario and evaluation tags.

The cases derive from the six locked business scenarios, verified generated tables, the
authorization matrix, and visually inspected ingested PDFs. No reference answer depends on
the public CUAD examples because those files are provenance references and are not ingested.

## Reproducibility

Regenerate both artifacts with:

```powershell
uv run python -m business_brain.evaluation.golden_generator
```

Automated tests require exactly 50 unique questions, the locked category distribution,
valid role-policy outcomes, real ingested document/clause references, non-drifting scenario
facts, server-derived action policies, and an up-to-date JSON Schema.

Ruff passed and the complete project suite passed 229 tests.

Step 5.1 defines expectations only. Actual RAGAS, routing, citation, tool, and refusal scores
are calculated in Step 5.2 rather than being claimed in advance.
