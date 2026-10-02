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
