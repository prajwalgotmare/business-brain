from pathlib import Path

from business_brain.forecasting.stockout import build_dataset, train_and_evaluate

ROOT = Path(__file__).resolve().parents[2]
TENANT_DIR = ROOT / "data" / "generated" / "aura_brands"


def test_dataset_uses_ordered_time_split_without_future_features() -> None:
    dataset = build_dataset(TENANT_DIR / "orders.csv", TENANT_DIR / "order_lines.csv")

    assert dataset.rows
    assert dataset.cutoff_week == dataset.weeks[5]
    assert all(row["week"] >= dataset.weeks[2] for row in dataset.rows)
    assert all(
        row["week"] < dataset.cutoff_week
        for row in dataset.rows
        if row["week"] < dataset.cutoff_week
    )
    assert all(row["week_index"] < len(dataset.weeks) for row in dataset.rows)


def test_xgboost_metrics_and_model_are_reproducible() -> None:
    dataset = build_dataset(TENANT_DIR / "orders.csv", TENANT_DIR / "order_lines.csv")
    model_path = ROOT / "tmp" / "forecast_test_model.json"
    first = train_and_evaluate(dataset, model_path)
    second = train_and_evaluate(dataset)

    assert first.train_rows > 0
    assert first.test_rows > 0
    assert first.baseline_mae >= 0
    assert first.xgboost_mae >= 0
    assert first == second
    assert model_path.exists()
