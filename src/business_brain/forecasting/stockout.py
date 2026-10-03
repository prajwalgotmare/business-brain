"""Leakage-safe weekly demand forecasting for stockout screening."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

FEATURES = ("lag_1", "lag_2", "rolling_3", "week_index")


@dataclass(frozen=True)
class ForecastDataset:
    weeks: list[date]
    products: list[str]
    rows: list[dict[str, Any]]
    cutoff_week: date


@dataclass(frozen=True)
class ForecastMetrics:
    baseline_mae: float
    baseline_rmse: float
    xgboost_mae: float
    xgboost_rmse: float
    train_rows: int
    test_rows: int


def _week_start(value: str) -> date:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return parsed - timedelta(days=parsed.weekday())


def build_dataset(orders_path: Path, lines_path: Path) -> ForecastDataset:
    order_weeks: dict[str, date] = {}
    with orders_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            order_weeks[row["order_id"]] = _week_start(row["order_timestamp"])

    weekly: dict[tuple[str, date], float] = defaultdict(float)
    with lines_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            week = order_weeks.get(row["order_id"])
            if week is not None:
                weekly[(row["product_id"], week)] += float(row["quantity"])

    products = sorted({product for product, _ in weekly})
    observed_weeks = sorted({week for _, week in weekly})
    weeks = list(
        observed_weeks[0] + timedelta(weeks=index)
        for index in range((observed_weeks[-1] - observed_weeks[0]).days // 7 + 1)
    )
    cutoff_index = max(3, math.ceil(len(weeks) * 0.8))
    cutoff = weeks[cutoff_index]
    rows: list[dict[str, Any]] = []
    for product in products:
        values = [weekly.get((product, week), 0.0) for week in weeks]
        for index in range(2, len(weeks)):
            rows.append(
                {
                    "product_id": product,
                    "week": weeks[index],
                    "lag_1": values[index - 1],
                    "lag_2": values[index - 2],
                    "rolling_3": sum(values[max(0, index - 3) : index]) / 3,
                    "week_index": index,
                    "target": values[index],
                }
            )
    return ForecastDataset(weeks, products, rows, cutoff)


def _matrix(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([[row[feature] for feature in FEATURES] for row in rows], dtype=float),
        np.asarray([row["target"] for row in rows], dtype=float),
    )


def train_and_evaluate(dataset: ForecastDataset, model_path: Path | None = None) -> ForecastMetrics:
    train = [row for row in dataset.rows if row["week"] < dataset.cutoff_week]
    test = [row for row in dataset.rows if row["week"] >= dataset.cutoff_week]
    if not train or not test:
        raise ValueError("time split must produce both training and test rows")
    x_train, y_train = _matrix(train)
    x_test, y_test = _matrix(test)
    baseline = x_test[:, 0]
    model = xgb.train(
        {
            "objective": "reg:squarederror",
            "max_depth": 3,
            "eta": 0.05,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "seed": 42,
            "nthread": 1,
        },
        xgb.DMatrix(x_train, label=y_train, feature_names=list(FEATURES)),
        num_boost_round=20,
    )
    prediction = np.maximum(
        model.predict(xgb.DMatrix(x_test, feature_names=list(FEATURES))), 0
    )
    if model_path is not None:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(model_path))
    return ForecastMetrics(
        baseline_mae=float(np.mean(np.abs(baseline - y_test))),
        baseline_rmse=float(np.sqrt(np.mean((baseline - y_test) ** 2))),
        xgboost_mae=float(np.mean(np.abs(prediction - y_test))),
        xgboost_rmse=float(np.sqrt(np.mean((prediction - y_test) ** 2))),
        train_rows=len(train),
        test_rows=len(test),
    )
