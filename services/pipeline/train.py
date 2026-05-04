from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3

from services.pipeline.backtest import (
    BacktestReport,
    build_backtest_artifact_name,
    run_rolling_backtest,
    write_backtest_artifact,
)
from services.pipeline.datasets import DatasetBundle, build_dataset_bundle, register_dataset, write_dataset_artifact
from services.pipeline.models import (
    DEFAULT_PRICE_REGRESSOR_EPOCHS,
    DEFAULT_PRICE_REGRESSOR_LEARNING_RATE,
    PRICE_MODEL_LOGIC_VERSION,
    TREND_MODEL_LOGIC_VERSION,
    fit_price_regressor,
    fit_trend_model,
    serialize_price_regressor,
    serialize_trend_model,
)
from services.pipeline.registry import (
    ModelRegistration,
    build_model_registration,
    register_model,
    write_model_artifact,
)


@dataclass(frozen=True)
class PhaseTwoArtifacts:
    dataset_bundle: DatasetBundle
    backtest_report: BacktestReport
    trend_registration: ModelRegistration
    price_registration: ModelRegistration
    backtest_artifact_name: str



def run_phase_two_training(
    connection: sqlite3.Connection,
    symbols: list[str],
    timeframe: str,
    horizon: str,
) -> PhaseTwoArtifacts:
    dataset_bundle = build_dataset_bundle(connection, symbols, timeframe, horizon)
    backtest_report = run_rolling_backtest(dataset_bundle)
    trend_model = fit_trend_model(dataset_bundle.rows)
    price_model = fit_price_regressor(dataset_bundle.rows)

    trend_model_payload = serialize_trend_model(trend_model)
    price_model_payload = serialize_price_regressor(price_model)
    training_run_id = _build_training_run_id(
        dataset_bundle.dataset_version,
        timeframe,
        horizon,
        dataset_bundle.symbols,
        trend_model_payload,
        price_model_payload,
    )
    training_window_start = min(row.forecast_time for row in dataset_bundle.rows)
    training_window_end = max(row.target_time for row in dataset_bundle.rows)
    trend_registration = build_model_registration(
        model_family="nearest-centroid-classifier",
        dataset_version=dataset_bundle.dataset_version,
        timeframe=timeframe,
        horizon=horizon,
        symbols=dataset_bundle.symbols,
        metrics={
            "direction_accuracy": backtest_report.aggregate.direction_accuracy,
            "sample_count": float(backtest_report.aggregate.sample_count),
        },
        training_run_id=training_run_id,
        training_window_start=training_window_start,
        training_window_end=training_window_end,
        feature_schema_version=dataset_bundle.feature_schema_version,
        logic_version=TREND_MODEL_LOGIC_VERSION,
        hyperparameters={"mode": "centroid-distance"},
        model_payload=trend_model_payload,
    )
    price_registration = build_model_registration(
        model_family="linear-price-regressor",
        dataset_version=dataset_bundle.dataset_version,
        timeframe=timeframe,
        horizon=horizon,
        symbols=dataset_bundle.symbols,
        metrics={
            "mean_absolute_error": backtest_report.aggregate.mean_absolute_error,
            "mean_absolute_percentage_error": backtest_report.aggregate.mean_absolute_percentage_error,
            "sample_count": float(backtest_report.aggregate.sample_count),
        },
        training_run_id=training_run_id,
        training_window_start=training_window_start,
        training_window_end=training_window_end,
        feature_schema_version=dataset_bundle.feature_schema_version,
        logic_version=PRICE_MODEL_LOGIC_VERSION,
        hyperparameters={
            "epochs": DEFAULT_PRICE_REGRESSOR_EPOCHS,
            "learning_rate": DEFAULT_PRICE_REGRESSOR_LEARNING_RATE,
        },
        model_payload=price_model_payload,
    )
    backtest_artifact_name = build_backtest_artifact_name(
        dataset_bundle.dataset_version,
        trend_registration.model_version,
        price_registration.model_version,
    )

    with connection:
        write_dataset_artifact(dataset_bundle)
        write_model_artifact(trend_registration)
        write_model_artifact(price_registration)
        write_backtest_artifact(backtest_report, backtest_artifact_name)
        register_dataset(connection, dataset_bundle)
        register_model(connection, trend_registration)
        register_model(connection, price_registration)

    return PhaseTwoArtifacts(
        dataset_bundle=dataset_bundle,
        backtest_report=backtest_report,
        trend_registration=trend_registration,
        price_registration=price_registration,
        backtest_artifact_name=backtest_artifact_name,
    )



def _build_training_run_id(
    dataset_version: str,
    timeframe: str,
    horizon: str,
    symbols: list[str],
    trend_model_payload: dict,
    price_model_payload: dict,
) -> str:
    digest = sha256(
        json.dumps(
            {
                "dataset_version": dataset_version,
                "timeframe": timeframe,
                "horizon": horizon,
                "symbols": symbols,
                "trend_model_payload": trend_model_payload,
                "price_model_payload": price_model_payload,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"train-{digest}"
