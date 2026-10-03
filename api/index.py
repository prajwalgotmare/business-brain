"""Vercel entrypoint for the Business Brain FastAPI application."""

from pathlib import Path
import sys


# Vercel invokes this module from the repository root.  The application uses
# the standard ``src`` layout, so expose that package before importing it.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from business_brain.main import app  # noqa: E402

__all__ = ["app"]
