from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_demo_shell_contains_governed_features() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "Business Brain" in html
    assert "data-question" in html
    assert "/agent/run" in app
    assert "/uploads/preview" in app
    assert "X-Tenant-ID" in app
    assert "X-Role" in app
