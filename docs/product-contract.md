# Business Brain - Product Contract

## Purpose

Business Brain is a high-fidelity portfolio demonstration of a governed enterprise
operations agent. Its primary goal is to demonstrate Applied AI and LLM systems
engineering through measurable architecture, reliability, security, and evaluation.

## Demonstration company

- Primary tenant: Aura Brands
- Adversarial tenant: Apex Retail
- Domain pillars: e-commerce, logistics, and commercial finance/accounting
- Data policy: public and synthetic data only

## Personas

| Role | Permitted scope | Explicit restrictions |
| --- | --- | --- |
| Founder / CFO | Full tenant access and high-risk approvals | Cannot access another tenant |
| Logistics Manager | Inventory, shipments, carrier performance, packing slips | No profit margins or accounting ledgers |
| Staff Accountant | Invoices, ledgers, tax dates, freight billing audits | Cannot alter carrier contract terms |
| Support Intern | Order lookup, tracking, public return and shipping policies | No costs, supplier contracts, or ledgers |

## Governed actions

- Low risk: read-only questions, analytics, inventory checks, and tracking lookup.
- Medium risk: customer-delay drafts, internal reorder tickets, and invoice logging.
- High risk: carrier financial disputes, external purchase orders, and payment-term changes.

High-risk actions require Founder/CFO approval. The workflow must persist the pending
approval and resume from PostgreSQL after a process restart.

## MVP evidence

- Public interactive Aura Brands demo.
- Versioned 50-question golden evaluation set.
- At least 85% groundedness on the locked evaluation version.
- Retrieval/tool-routing P95 below 1.5 seconds under a documented test profile.
- Separately reported end-to-end generation latency.
- Zero failures in the versioned cross-tenant and role-isolation adversarial suite.
- Demonstrated crash-resume of an interrupted approval.
- Reproducible README, architecture diagrams, and measured resume bullets.

## Non-goals for the MVP

- Processing real customer or patient data.
- Automatically dispatching external financial or purchasing actions.
- Claiming absolute security or production SLA guarantees from free-tier services.
- Starting with a multi-agent architecture before the governed single-agent baseline is measured.

