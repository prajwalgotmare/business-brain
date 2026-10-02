"""Generate or verify the six-scenario evaluation answer-key manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_brain.data import (
    GroundTruthManifest,
    build_commerce_inventory_dataset,
    build_finance_dataset,
    build_ground_truth_manifest,
    build_logistics_dataset,
    build_reference_catalog,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "data" / "evaluation" / "ground_truth_scenarios.json"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schemas" / "scenario_ground_truth.schema.json"


def _json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_artifacts() -> dict[Path, str]:
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    logistics = build_logistics_dataset(catalog, commerce)
    finance = build_finance_dataset(catalog, commerce, logistics)
    manifest = build_ground_truth_manifest(catalog, commerce, logistics, finance)
    return {
        MANIFEST_PATH: _json(manifest.model_dump(mode="json")),
        SCHEMA_PATH: _json(GroundTruthManifest.model_json_schema()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = render_artifacts()
    if args.check:
        stale = [
            path
            for path, expected in artifacts.items()
            if not path.exists() or path.read_text(encoding="utf-8") != expected
        ]
        for path in stale:
            print(f"stale: {path.relative_to(PROJECT_ROOT)}")
        if stale:
            return 1
        print("scenario ground-truth artifacts are current")
        return 0
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
