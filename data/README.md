# Demo data

All data in this directory is synthetic. It must not contain real customer, employee,
supplier, payment, credential, or address information.

## Directory contract

- `seeds/reference_catalog.json` is the deterministic master catalog shared by every
  later commerce, logistics, finance, document, and evaluation generator.
- `schemas/reference_catalog.schema.json` is generated from the strict Pydantic catalog
  contract and supports machine validation outside Python.
- `generated/aura_brands/` and `generated/apex_retail/` contain tenant-separated CSV
  exports. The commerce step creates customers, orders, order lines, inventory balances,
  and inventory movements.
- `schemas/commerce_inventory.schema.json` describes the combined commerce/inventory
  contract used to validate the CSV source collections before database ingestion.
- Logistics generation adds shipments, shipment items, tracking events, SLA facts,
  delivery exceptions, and carrier manifest entries to each tenant directory.
- `schemas/logistics.schema.json` describes the combined logistics contract.
- Procurement and finance generation adds purchase orders, purchase-order lines,
  vendor invoices, invoice lines, payments, and weekly regional margin snapshots.
- `schemas/finance.schema.json` describes the combined procurement/finance contract.
- `sources/public_calibration.json` records source URLs, licenses, aggregate profile
  statistics, intended uses, and transformations. Raw public records are not committed.

Regenerate the catalog and schema:

```powershell
uv run python scripts/generate_reference_data.py
```

Verify that committed files match the generator without changing them:

```powershell
uv run python scripts/generate_reference_data.py --check
```

The fixed seed is `20261003`. Identifiers remain stable across regenerations so
transactions, documents, evaluation questions, and citations can safely reference them.

Generate the commerce and inventory CSV files:

```powershell
uv run python scripts/generate_commerce_inventory_data.py
```

Verify that the committed CSV files and schema match the deterministic generator:

```powershell
uv run python scripts/generate_commerce_inventory_data.py --check
```

The commerce generator uses seed `20261004`, a fixed six-week order window beginning
2026-08-10, and a snapshot cutoff of 2026-09-21T23:59:59Z.

Generate and verify the logistics CSV files:

```powershell
uv run python scripts/generate_logistics_data.py
uv run python scripts/generate_logistics_data.py --check
```

The logistics generator uses seed `20261005`. Inbound shipments contain deterministic
purchase-order references that the procurement generator must materialize in Step 3.5.

Generate and verify the procurement and finance CSV files:

```powershell
uv run python scripts/generate_finance_data.py
uv run python scripts/generate_finance_data.py --check
```

The finance generator uses seed `20261006`. It materializes every inbound shipment as
an approved purchase order, reconciles supplier and carrier invoices to source lines,
applies completed payments, and derives weekly regional margins from commerce and
outbound freight data.
