"""Small dependency-free experiment manifest compatible with DagsHub uploads."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_experiment_manifest(
    *,
    run_name: str,
    parameters: dict[str, Any],
    metrics: dict[str, float],
    artifacts: list[Path],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_name": run_name,
        "created_at": datetime.now(UTC).isoformat(),
        "tracker": {"name": "DagsHub", "mode": "local_manifest"},
        "parameters": parameters,
        "metrics": metrics,
        "artifacts": [
            {"path": str(path), "sha256": sha256_file(path)} for path in artifacts
        ],
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
