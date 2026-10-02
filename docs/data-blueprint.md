# Business Brain Data Blueprint

## Status and scope

This document is the authoritative contract for Phase 3 demo data. It defines the
canonical business entities, identifiers, relationships, access classifications, and
quality rules that all generators, database migrations, ingestion jobs, retrieval
filters, and evaluation fixtures must follow.

This phase uses public references and synthetic records only. It does not contain or
permit real customer, employee, supplier, or payment data.

The model is standards-informed rather than a claim of complete certification:

- DataCo SMART Supply Chain supplies realistic commerce and delivery terminology.
- UCI Online Retail II supplies profiled transaction-size, quantity, and cancellation
  reference distributions; only aggregate statistics are retained.
- GS1 EPCIS 2.0 informs shipment and tracking-event semantics.
- OASIS UBL 2.3 informs purchase-order and invoice concepts.
- The U.S. Bureau of Labor Statistics Producer Price Index supplies public freight-cost
  terminology and a future index-calibration source.
- JSON payloads are validated against JSON Schema Draft 2020-12 through generated
  Pydantic schemas.

## Data flow and storage contract

```text
CSV batch exports ---------+
JSON carrier events -------+--> validation --> canonical records --> Neon PostgreSQL
PDF business documents ----+          |                    +-------> Qdrant chunks
                                       +--> quarantine on failure

Website --> FastAPI --> governed LangGraph agent --> SQL and/or hybrid retrieval
```

- CSV and JSON are ingestion and interchange formats, not independent sources of
  truth after validation.
- PostgreSQL is the canonical source for structured operational and financial data.
- Qdrant contains document chunks and retrieval metadata, never authorization truth.
- PDF metadata and access policy remain in PostgreSQL; every Qdrant point repeats the
  immutable tenant and sensitivity filters needed for retrieval isolation.
- The website never connects directly to PostgreSQL or Qdrant. It calls FastAPI, which
  supplies the authenticated tenant and role to governed tools.

## Global conventions

| Concern | Contract |
| --- | --- |
| Tenant boundary | Every business record has a non-null `tenant_id`; all keys and queries are tenant-scoped. |
| Primary keys | Deterministic text identifiers for fixtures, such as `ord_aur_000001`; UUIDs may be added for production-facing APIs later. |
| Foreign keys | Stored explicitly and validated before ingestion. |
| Naming | `snake_case` fields; singular entity names; plural file and table names. |
| Timestamps | ISO 8601/RFC 3339 UTC values, stored as timezone-aware timestamps. |
| Business dates | ISO 8601 calendar dates where time-of-day is irrelevant. |
| Money | Decimal amounts with explicit ISO 4217 `currency_code`; never binary floating point. |
| Quantities | Decimal or integer plus an explicit unit code; no negative on-hand quantity. |
| Countries | ISO 3166-1 alpha-2 codes. |
| Nulls | Used only when a field is genuinely unknown or not applicable, never as an undocumented sentinel. |
| Booleans | `true`/`false`, not `Y`/`N`, `0`/`1`, or blank. |
| Enumerations | Lowercase `snake_case` values controlled by the schema. |
| Soft deletion | `record_status` is `active`, `inactive`, or `cancelled`; fixture rows are not physically deleted. |
| Provenance | Each ingested record carries `source_system`, `source_file`, and `ingested_at`. |
| Reproducibility | Synthetic generation uses a documented seed and produces a manifest with row counts and hashes. |

### Tenant prefixes

| Tenant | `tenant_id` | Identifier prefix |
| --- | --- | --- |
| Aura Brands | `tenant_aura` | `aur` |
| Apex Retail | `tenant_apex` | `apx` |

The prefix makes fixtures readable, but authorization must always use `tenant_id` and
must never depend on parsing an identifier prefix.

## Access classification

Each record or document has one `sensitivity` value. Roles may read a sensitivity only
when both the tenant filter and the role policy permit it.

| Sensitivity | Typical content | Permitted roles |
| --- | --- | --- |
| `public` | Published shipping/return policies | Founder/CFO, logistics manager, staff accountant, support intern |
| `support` | Customer order status and tracking link | Founder/CFO, logistics manager, support intern |
| `operations` | Inventory, warehouses, shipments, carrier performance | Founder/CFO, logistics manager |
| `accounting` | Vendor invoices, payments, freight audit details | Founder/CFO, staff accountant |
| `executive` | Costs, margins, negotiated price tiers, approval records | Founder/CFO |

Data may be further restricted by resource or action policy. For example, an accountant
may read a carrier agreement for an invoice audit but cannot modify its terms. The
sensitivity value is therefore a retrieval filter, not the complete authorization
decision.

## Canonical entities

Fields marked **FK** reference another canonical entity. All entities also receive the
global provenance fields during ingestion.

### Identity and reference data

#### `tenants`

| Field | Type | Rules |
| --- | --- | --- |
| `tenant_id` | text | Primary key |
| `tenant_name` | text | Unique display name |
| `default_currency_code` | char(3) | ISO 4217 |
| `timezone` | text | IANA timezone name |
| `record_status` | enum | Must be `active` for demo access |

#### `regions`

| Field | Type | Rules |
| --- | --- | --- |
| `region_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `region_name` | text | Demo values include East, Central, and West |
| `country_code` | char(2) | ISO 3166-1 alpha-2 |
| `sensitivity` | enum | `operations` |

#### `products`

| Field | Type | Rules |
| --- | --- | --- |
| `product_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `sku` | text | Unique within tenant |
| `product_name` | text | Synthetic consumer-goods name |
| `category` | text | Controlled generator vocabulary |
| `unit_of_measure` | text | UNECE-compatible code where practical |
| `list_price` | decimal(12,2) | Non-negative |
| `standard_cost` | decimal(12,2) | Non-negative and normally below list price |
| `currency_code` | char(3) | ISO 4217 |
| `reorder_point` | integer | Non-negative |
| `safety_stock` | integer | Non-negative |
| `record_status` | enum | Global status vocabulary |
| `sensitivity` | enum | `operations`; cost fields require executive projection |

#### `warehouses`

| Field | Type | Rules |
| --- | --- | --- |
| `warehouse_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `region_id` | text | **FK** regions |
| `warehouse_name` | text | Unique within tenant |
| `country_code` | char(2) | ISO 3166-1 alpha-2 |
| `timezone` | text | IANA timezone name |
| `sensitivity` | enum | `operations` |

#### `suppliers`

| Field | Type | Rules |
| --- | --- | --- |
| `supplier_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `supplier_name` | text | Synthetic company name |
| `payment_terms_days` | integer | Controlled values such as 30 or 60 |
| `lead_time_days` | integer | Positive |
| `currency_code` | char(3) | ISO 4217 |
| `record_status` | enum | Global status vocabulary |
| `sensitivity` | enum | `accounting` |

#### `carriers`

| Field | Type | Rules |
| --- | --- | --- |
| `carrier_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `carrier_name` | text | Synthetic or clearly marked demo carrier identity |
| `service_level` | enum | `standard`, `expedited`, or `same_day` |
| `sla_delivery_days` | integer | Positive |
| `record_status` | enum | Global status vocabulary |
| `sensitivity` | enum | `operations` |

### Commerce and inventory

#### `customers`

| Field | Type | Rules |
| --- | --- | --- |
| `customer_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `customer_segment` | enum | `consumer`, `small_business`, or `wholesale` |
| `region_id` | text | **FK** regions |
| `display_name` | text | Synthetic; no real person |
| `email_alias` | text | Reserved `.example` domain only |
| `sensitivity` | enum | `support` |

#### `orders`

| Field | Type | Rules |
| --- | --- | --- |
| `order_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `customer_id` | text | **FK** customers |
| `warehouse_id` | text | **FK** warehouses |
| `order_timestamp` | timestamptz | Cannot be in the fixture future |
| `order_status` | enum | `pending`, `allocated`, `shipped`, `delivered`, `cancelled`, or `returned` |
| `sales_channel` | enum | `web`, `marketplace`, or `wholesale` |
| `currency_code` | char(3) | Must match line amounts |
| `subtotal_amount` | decimal(12,2) | Sum of line net amounts |
| `discount_amount` | decimal(12,2) | Non-negative |
| `tax_amount` | decimal(12,2) | Non-negative |
| `shipping_amount` | decimal(12,2) | Non-negative |
| `order_total_amount` | decimal(12,2) | Reconciles to components |
| `sensitivity` | enum | `support` |

#### `order_lines`

| Field | Type | Rules |
| --- | --- | --- |
| `order_line_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `order_id` | text | **FK** orders |
| `product_id` | text | **FK** products |
| `quantity` | integer | Positive |
| `unit_price` | decimal(12,2) | Non-negative |
| `discount_amount` | decimal(12,2) | Non-negative |
| `net_amount` | decimal(12,2) | `quantity * unit_price - discount_amount` |
| `unit_cost_snapshot` | decimal(12,2) | Non-negative; executive-only projection |
| `sensitivity` | enum | `support`; cost field requires executive projection |

#### `inventory_balances`

| Field | Type | Rules |
| --- | --- | --- |
| `inventory_balance_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `warehouse_id` | text | **FK** warehouses |
| `product_id` | text | **FK** products |
| `snapshot_at` | timestamptz | One balance per product/warehouse/snapshot |
| `on_hand_quantity` | integer | Non-negative |
| `allocated_quantity` | integer | Between zero and on-hand |
| `available_quantity` | integer | `on_hand_quantity - allocated_quantity` |
| `inbound_quantity` | integer | Non-negative |
| `sensitivity` | enum | `operations` |

#### `inventory_movements`

| Field | Type | Rules |
| --- | --- | --- |
| `inventory_movement_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `warehouse_id` | text | **FK** warehouses |
| `product_id` | text | **FK** products |
| `occurred_at` | timestamptz | UTC |
| `movement_type` | enum | `receipt`, `allocation`, `shipment`, `return`, or `adjustment` |
| `quantity_delta` | integer | Signed; zero prohibited |
| `reference_type` | enum | `order`, `purchase_order`, `return`, or `adjustment` |
| `reference_id` | text | Resolves to matching reference type |
| `sensitivity` | enum | `operations` |

### Logistics

#### `shipments`

| Field | Type | Rules |
| --- | --- | --- |
| `shipment_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `order_id` | text | **FK** orders for outbound shipments; nullable for inbound |
| `purchase_order_id` | text | **FK** purchase orders for inbound shipments; nullable for outbound |
| `carrier_id` | text | **FK** carriers |
| `origin_warehouse_id` | text | **FK** warehouses when applicable |
| `destination_region_id` | text | **FK** regions |
| `tracking_number` | text | Unique within tenant/carrier |
| `shipped_at` | timestamptz | Not before order or purchase-order creation |
| `promised_delivery_at` | timestamptz | Not before shipped time |
| `delivered_at` | timestamptz | Nullable until delivered |
| `shipment_status` | enum | `label_created`, `in_transit`, `delayed`, `delivered`, `exception`, or `cancelled` |
| `freight_charge_amount` | decimal(12,2) | Non-negative |
| `currency_code` | char(3) | ISO 4217 |
| `sensitivity` | enum | `operations`; freight charge requires accounting projection |

#### `tracking_events`

| Field | Type | Rules |
| --- | --- | --- |
| `tracking_event_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `shipment_id` | text | **FK** shipments |
| `event_time` | timestamptz | Monotonic within a shipment except corrected events |
| `event_type` | enum | `picked_up`, `departed`, `arrived`, `out_for_delivery`, `delivered`, `delay`, or `exception` |
| `location_code` | text | Synthetic facility/location identifier |
| `reason_code` | text | Required for delay and exception events |
| `event_source` | enum | `carrier_webhook` or `batch_manifest` |
| `raw_event_id` | text | Idempotency key unique within tenant/source |
| `sensitivity` | enum | `support` for customer-safe projection; otherwise `operations` |

### Procurement and finance

#### `purchase_orders`

| Field | Type | Rules |
| --- | --- | --- |
| `purchase_order_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `supplier_id` | text | **FK** suppliers |
| `warehouse_id` | text | **FK** warehouses |
| `created_at` | timestamptz | UTC |
| `expected_at` | timestamptz | After creation |
| `purchase_order_status` | enum | `draft`, `pending_approval`, `approved`, `sent`, `partially_received`, `received`, or `cancelled` |
| `currency_code` | char(3) | ISO 4217 |
| `subtotal_amount` | decimal(12,2) | Sum of lines |
| `tax_amount` | decimal(12,2) | Non-negative |
| `freight_amount` | decimal(12,2) | Non-negative |
| `total_amount` | decimal(12,2) | Reconciles to components |
| `approval_required` | boolean | True for all external demo POs |
| `sensitivity` | enum | `executive` |

#### `purchase_order_lines`

| Field | Type | Rules |
| --- | --- | --- |
| `purchase_order_line_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `purchase_order_id` | text | **FK** purchase orders |
| `product_id` | text | **FK** products |
| `quantity` | integer | Positive |
| `unit_cost` | decimal(12,2) | Non-negative |
| `line_amount` | decimal(12,2) | `quantity * unit_cost` |
| `sensitivity` | enum | `executive` |

#### `vendor_invoices`

| Field | Type | Rules |
| --- | --- | --- |
| `vendor_invoice_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `supplier_id` | text | **FK** suppliers; carriers are represented as freight suppliers when billed |
| `purchase_order_id` | text | **FK** purchase orders when applicable |
| `invoice_number` | text | Unique within tenant/supplier |
| `invoice_date` | date | Not after ingestion date |
| `due_date` | date | On or after invoice date |
| `invoice_status` | enum | `open`, `partially_paid`, `paid`, `overdue`, `disputed`, or `void` |
| `currency_code` | char(3) | ISO 4217 |
| `subtotal_amount` | decimal(12,2) | Sum of lines |
| `tax_amount` | decimal(12,2) | Non-negative |
| `total_amount` | decimal(12,2) | Reconciles to components |
| `outstanding_amount` | decimal(12,2) | Total minus applied payments/credits |
| `sensitivity` | enum | `accounting` |

#### `vendor_invoice_lines`

| Field | Type | Rules |
| --- | --- | --- |
| `vendor_invoice_line_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `vendor_invoice_id` | text | **FK** vendor invoices |
| `line_type` | enum | `product`, `freight`, `fuel_surcharge`, `tax`, `credit`, or `other` |
| `description` | text | Synthetic description |
| `shipment_id` | text | **FK** shipments when a freight line is auditable |
| `quantity` | decimal(12,3) | Positive unless line is a credit |
| `unit_price` | decimal(12,2) | Signed only for credit lines |
| `line_amount` | decimal(12,2) | Reconciles to quantity and unit price |
| `sensitivity` | enum | `accounting` |

#### `payments`

| Field | Type | Rules |
| --- | --- | --- |
| `payment_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `vendor_invoice_id` | text | **FK** vendor invoices |
| `payment_date` | date | On or after invoice date |
| `payment_amount` | decimal(12,2) | Positive and not above outstanding balance without a documented credit |
| `currency_code` | char(3) | Must match invoice |
| `payment_status` | enum | `scheduled`, `completed`, `failed`, or `cancelled` |
| `sensitivity` | enum | `accounting` |

#### `regional_margin_snapshots`

This is a derived analytical table, not an independent financial source of truth.

| Field | Type | Rules |
| --- | --- | --- |
| `margin_snapshot_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `region_id` | text | **FK** regions |
| `week_start_date` | date | ISO week start |
| `revenue_amount` | decimal(12,2) | Reconciles to qualifying order lines |
| `cost_of_goods_amount` | decimal(12,2) | Reconciles to cost snapshots |
| `freight_expense_amount` | decimal(12,2) | Reconciles to allocated freight lines |
| `refund_amount` | decimal(12,2) | Non-negative |
| `net_profit_amount` | decimal(12,2) | Revenue minus modeled costs and refunds |
| `net_margin_pct` | decimal(7,4) | Net profit divided by revenue when revenue is non-zero |
| `calculated_at` | timestamptz | UTC |
| `sensitivity` | enum | `executive` |

### Documents and governance

#### `documents`

| Field | Type | Rules |
| --- | --- | --- |
| `document_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `document_type` | enum | `supplier_agreement`, `carrier_agreement`, `vendor_invoice`, `policy`, or `compliance_calendar` |
| `title` | text | Synthetic title |
| `effective_date` | date | Required for agreements/policies |
| `expiration_date` | date | Nullable; after effective date when present |
| `related_entity_type` | text | Supplier, carrier, invoice, or tenant |
| `related_entity_id` | text | Resolves within the same tenant |
| `storage_uri` | text | Internal demo object path, not a public secret URL |
| `content_sha256` | char(64) | Integrity and duplicate detection |
| `sensitivity` | enum | Based on document content |

#### `document_chunks`

| Field | Type | Rules |
| --- | --- | --- |
| `chunk_id` | text | Primary key and Qdrant point identity |
| `tenant_id` | text | **FK** tenants and mandatory Qdrant payload filter |
| `document_id` | text | **FK** documents |
| `chunk_index` | integer | Zero-based and unique within document |
| `section_heading` | text | Nullable |
| `page_number` | integer | Positive when available |
| `clause_id` | text | Stable citation label where applicable |
| `content` | text | Extracted synthetic content |
| `content_sha256` | char(64) | Chunk integrity |
| `sensitivity` | enum | Cannot be less restrictive than parent document |

#### `approval_requests`

| Field | Type | Rules |
| --- | --- | --- |
| `approval_request_id` | text | Primary key within tenant |
| `tenant_id` | text | **FK** tenants |
| `thread_id` | text | LangGraph thread/checkpoint identity |
| `action_type` | enum | `purchase_order`, `carrier_dispute`, `payment_term_change`, or medium-risk draft action |
| `risk_level` | enum | `medium` or `high` |
| `requested_by_role` | enum | Authenticated role at request time |
| `required_approver_role` | enum | Derived by policy, not model output |
| `payload` | jsonb | Validated action draft |
| `approval_status` | enum | `pending`, `approved`, `rejected`, `expired`, or `cancelled` |
| `created_at` | timestamptz | UTC |
| `decided_at` | timestamptz | Nullable until decided |
| `sensitivity` | enum | `executive` for high risk; otherwise resource-derived |

## Structured JSON event profile

Carrier webhooks use a versioned envelope. The ingestion API derives `tenant_id` from
the authenticated integration identity; a tenant supplied only inside the payload is
never trusted for authorization.

```json
{
  "schema_version": "1.0",
  "event_id": "evt_aur_000001",
  "event_type": "shipment.delay",
  "occurred_at": "2026-09-14T10:30:00Z",
  "source": "carrier_demo_north",
  "data": {
    "tracking_number": "TRK-AUR-000042",
    "status": "delayed",
    "location_code": "US-WEST-HUB-02",
    "reason_code": "weather",
    "estimated_delivery_at": "2026-09-16T18:00:00Z"
  }
}
```

Required ingestion behavior:

1. Authenticate the integration and establish tenant context.
2. Validate `schema_version`, event type, timestamp, and data shape.
3. Enforce idempotency on tenant, source, and event ID.
4. Resolve the tracking number only inside that tenant.
5. Store the raw payload for audit with a bounded retention policy.
6. Upsert the canonical tracking event and recompute shipment status.
7. Reject or quarantine unknown, malformed, cross-tenant, or out-of-order updates.

## Cross-entity integrity rules

1. Every foreign-key target belongs to the same tenant as its source record.
2. An outbound shipment references an order; an inbound shipment references a purchase
   order. A fixture cannot ambiguously represent both.
3. Delivered shipments have a delivered event and `delivered_at`; undelivered shipments
   do not.
4. Order totals equal line subtotals minus order discounts plus tax and shipping.
5. Purchase-order and vendor-invoice totals reconcile to their lines and adjustments.
6. Completed payments reduce invoice outstanding amounts; cancelled or failed payments
   do not.
7. Inventory balance is reproducible from its opening balance and movements for the
   same product, warehouse, and cutoff time.
8. A document chunk inherits its tenant and cannot have a less restrictive sensitivity
   than its parent document.
9. Derived margin snapshots reconcile to their source orders, costs, refunds, and
   freight allocations for the same tenant, region, and week.
10. Synthetic email addresses use reserved `.example` domains and files contain no
    real credentials, bank accounts, payment cards, or personal addresses.

## Required demonstration scenarios

The generator must create deterministic scenario IDs and an answer-key manifest for:

| Scenario | Required connected evidence |
| --- | --- |
| Weekly stockout risk | High-velocity SKU, low available inventory, delayed inbound shipment, and reorder threshold |
| Carrier freight overbilling | Shipment logs, carrier invoice lines, agreement clause, SLA breach, and expected credit |
| Supplier commercial terms | Supplier record and cited agreement clauses for price tier and Net-30/60 terms |
| Overdue invoices | Open invoice, calculated due date, outstanding amount, and cited late-penalty clause |
| West Region margin decline | Week 2 and Week 3 orders, costs, refunds/freight variance, and reconciled margin snapshots |
| Purchase-order approval | Draft replenishment PO whose submission is blocked pending Founder/CFO approval |

Scenario rows must remain realistic enough for analytics, but their ground truth must be
unambiguous enough for automated evaluation.

## Planned Phase 3A file contract

No files in this section are generated in the blueprint step. Later generator steps will
produce them from one deterministic model:

```text
data/
|-- schemas/                 # machine-readable schema contracts
|-- generated/
|   |-- aura_brands/         # primary demo tenant CSV/JSON files
|   `-- apex_retail/         # isolation-test tenant CSV/JSON files
|-- seeds/                   # stable reference and scenario definitions
`-- README.md                # data dictionary, regeneration, and provenance

scripts/generate_demo_data.py
tests/data/
```

The generated manifest will record schema version, generator version, random seed, file
hashes, row counts, currency, time window, and expected scenario identifiers.

## Blueprint exit criteria

This blueprint is complete when:

- every required product question maps to named canonical entities;
- all entity relationships and tenant boundaries are explicit;
- money, timestamp, identifier, null, and enumeration rules are locked;
- role-facing sensitivity classifications are defined;
- required generated scenarios have objective connected evidence; and
- later schemas and generators can be reviewed against this document without inventing
  new core business concepts.
