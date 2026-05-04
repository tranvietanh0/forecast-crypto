from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from services.pipeline.artifacts import write_json_artifact
from services.pipeline.datasets import DatasetBundle
from services.pipeline.models import fit_price_regressor, fit_trend_model


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "metadata"
BACKTEST_LOGIC_VERSION = "1.0"


@dataclass(frozen=True)
class BacktestMetrics:
    direction_accuracy: float
    mean_absolute_error: float
    mean_absolute_percentage_error: float
    sample_count: int


@dataclass(frozen=True)
class BacktestReport:
    dataset_version: str
    timeframe: str
    horizon: str
    per_symbol: dict[str, BacktestMetrics]
    aggregate: BacktestMetrics


class BacktestError(RuntimeError):
    pass



def run_rolling_backtest(
    dataset_bundle: DatasetBundle,
    min_train_size: int = 8,
    step_size: int = 2,
) -> BacktestReport:
    per_symbol: dict[str, BacktestMetrics] = {}
    aggregate_predictions: list[tuple[int, int, float, float]] = []

    for symbol in dataset_bundle.symbols:
        rows = [row for row in dataset_bundle.rows if row.symbol == symbol]
        if len(rows) <= min_train_size:
            continue

        symbol_predictions: list[tuple[int, int, float, float]] = []
        test_start = min_train_size
        while test_start < len(rows):
            train_rows = rows[:test_start]
            test_rows = rows[test_start: test_start + step_size]
            if not test_rows:
                break

            trend_model = fit_trend_model(train_rows)
            price_model = fit_price_regressor(train_rows)
            for row in test_rows:
                trend_prediction = trend_model.predict(row)
                price_prediction = price_model.predict(row)
                symbol_predictions.append(
                    (
                        trend_prediction.label,
                        row.trend_label,
                        price_prediction.target_price,
                        row.target_price,
                    )
                )
            test_start += step_size

        if not symbol_predictions:
            continue
        metrics = _compute_metrics(symbol_predictions)
        per_symbol[symbol] = metrics
        aggregate_predictions.extend(symbol_predictions)

    if not aggregate_predictions:
        raise BacktestError("Backtest could not generate any predictions")

    return BacktestReport(
        dataset_version=dataset_bundle.dataset_version,
        timeframe=dataset_bundle.timeframe,
        horizon=dataset_bundle.horizon,
        per_symbol=per_symbol,
        aggregate=_compute_metrics(aggregate_predictions),
    )



def build_backtest_artifact_name(
    dataset_version: str,
    trend_model_version: str,
    price_model_version: str,
) -> str:
    return (
        f"backtest-{dataset_version}"
        f"-{trend_model_version}"
        f"-{price_model_version}"
        f"-logic-{BACKTEST_LOGIC_VERSION}.json"
    )



def write_backtest_artifact(report: BacktestReport, artifact_name: str) -> None:
    artifact_path = ARTIFACTS_DIR / artifact_name
    write_json_artifact(
        artifact_path,
        {
            "dataset_version": report.dataset_version,
            "timeframe": report.timeframe,
            "horizon": report.horizon,
            "backtest_logic_version": BACKTEST_LOGIC_VERSION,
            "aggregate": {
                "direction_accuracy": report.aggregate.direction_accuracy,
                "mean_absolute_error": report.aggregate.mean_absolute_error,
                "mean_absolute_percentage_error": report.aggregate.mean_absolute_percentage_error,
                "sample_count": report.aggregate.sample_count,
            },
            "per_symbol": {
                symbol: {
                    "direction_accuracy": metrics.direction_accuracy,
                    "mean_absolute_error": metrics.mean_absolute_error,
                    "mean_absolute_percentage_error": metrics.mean_absolute_percentage_error,
                    "sample_count": metrics.sample_count,
                }
                for symbol, metrics in report.per_symbol.items()
            },
        },
    )



def _compute_metrics(predictions: list[tuple[int, int, float, float]]) -> BacktestMetrics:
    correct = sum(1 for predicted, actual, _, _ in predictions if predicted == actual)
    absolute_errors = [abs(predicted_price - actual_price) for _, _, predicted_price, actual_price in predictions]
    percentage_errors = [
        abs((predicted_price - actual_price) / actual_price)
        for _, _, predicted_price, actual_price in predictions
        if actual_price != 0
    ]
    return BacktestMetrics(
        direction_accuracy=correct / len(predictions),
        mean_absolute_error=sum(absolute_errors) / len(absolute_errors),
        mean_absolute_percentage_error=(
            sum(percentage_errors) / len(percentage_errors) if percentage_errors else 0.0
        ),
        sample_count=len(predictions),
    )
