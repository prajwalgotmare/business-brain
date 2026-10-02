"""Generate or verify canonical reference-data artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_brain.data import ReferenceCatalog, build_reference_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "data" / "seeds" / "reference_catalog.json"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schemas" / "reference_catalog.schema.json"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_artifacts() -> dict[Path, str]:
    catalog = build_reference_catalog()
    return {
        CATALOG_PATH: _canonical_json(catalog.model_dump(mode="json")),
        SCHEMA_PATH: _canonical_json(ReferenceCatalog.model_json_schema()),
    }


def write_artifacts(artifacts: dict[Path, str]) -> None:
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def verify_artifacts(artifacts: dict[Path, str]) -> list[Path]:
    return [
        path
        for path, expected in artifacts.items()
        if not path.exists() or path.read_text(encoding="utf-8") != expected
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when committed artifacts do not match the deterministic catalog.",
    )
    args = parser.parse_args()
    artifacts = render_artifacts()

    if args.check:
        stale = verify_artifacts(artifacts)
        if stale:
            for path in stale:
                print(f"stale: {path.relative_to(PROJECT_ROOT)}")
            return 1
        print("reference-data artifacts are current")
        return 0

    write_artifacts(artifacts)
    for path in artifacts:
        print(f"wrote: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
