# Demo data

All data in this directory is synthetic. It must not contain real customer, employee,
supplier, payment, credential, or address information.

## Directory contract

- `seeds/reference_catalog.json` is the deterministic master catalog shared by every
  later commerce, logistics, finance, document, and evaluation generator.
- `schemas/reference_catalog.schema.json` is generated from the strict Pydantic catalog
  contract and supports machine validation outside Python.
- `generated/` will be introduced in later steps for tenant-separated CSV and JSON
  transaction files.

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
