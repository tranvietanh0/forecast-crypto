from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from contracts.events import ForecastDirection, ForecastGenerated, SCHEMA_VERSION
from contracts.timeframe import timeframe_to_timedelta
from services.inference.selectors import load_latest_model_versions
from services.inference.storage import (
    BATCH_STATUS_READY,
    count_batch_forecasts,
    ensure_forecast_batch,
    insert_forecast_records,
    load_batch_forecasts,
    load_batch_status,
    mark_batch_ready,
)
from services.pipeline.datasets import build_dataset_bundle
from services.pipeline.models import (
    deserialize_price_regressor,
    deserialize_trend_model,
    fit_price_regressor,
    fit_trend_model,
)
from services.pipeline.registry import load_model_artifact


class InferenceError(RuntimeError):
    pass



def build_batch_key(
    trend_model_version: str,
    price_model_version: str,
    symbols: list[str],
    timeframe: str,
    horizon: str,
    forecast_time: datetime,
) -> str:
    canonical_symbols = ",".join(sorted(symbols))
    return (
        f"{trend_model_version}:{price_model_version}:{canonical_symbols}:"
        f"{timeframe}:{horizon}:{forecast_time.isoformat()}"
    )



def run_inference_batch(
    connection: sqlite3.Connection,
    symbols: list[str],
    timeframe: str,
    horizon: str,
) -> tuple[str, list[ForecastGenerated]]:
    selected_models = load_latest_model_versions(connection, timeframe, horizon, symbols)
    trend_model_version = selected_models["nearest-centroid-classifier"]
    price_model_version = selected_models["linear-price-regressor"]

    dataset_bundle = build_dataset_bundle(connection, symbols, timeframe, horizon)
    if not dataset_bundle.rows:
        raise InferenceError("No dataset rows available for inference")

    trend_model = _load_trend_model(connection, trend_model_version)
    price_model = _load_price_model(connection, price_model_version)
    forecast_time = min(_latest_symbol_cutoff(dataset_bundle.rows, symbol) for symbol in dataset_bundle.symbols)
    batch_key = build_batch_key(
        trend_model_version,
        price_model_version,
        dataset_bundle.symbols,
        timeframe,
        horizon,
        forecast_time,
    )
    expected_count = len(dataset_bundle.symbols)

    with connection:
        batch_id, inserted = ensure_forecast_batch(
            connection,
            batch_key,
            trend_model_version,
            timeframe,
            horizon,
            dataset_bundle.symbols,
            forecast_time,
        )
        if not inserted:
            existing_status = load_batch_status(connection, batch_id)
            existing_forecasts = load_batch_forecasts(connection, batch_id)
            if existing_status == BATCH_STATUS_READY and len(existing_forecasts) == expected_count:
                return batch_id, existing_forecasts

        forecasts: list[ForecastGenerated] = []
        horizon_delta = timeframe_to_timedelta(horizon)
        for symbol in dataset_bundle.symbols:
            latest_row = _latest_dataset_row_at_or_before(dataset_bundle.rows, symbol, forecast_time)
            trend_prediction = trend_model.predict(latest_row)
            price_prediction = price_model.predict(latest_row)
            target_time = forecast_time + horizon_delta
            forecasts.append(
                ForecastGenerated(
                    schema_version=SCHEMA_VERSION,
                    event_id=ForecastGenerated.new_event_id(),
                    forecast_batch_id=batch_id,
                    model_version=trend_model_version,
                    aux_model_version=price_model_version,
                    symbol=symbol,
                    timeframe=timeframe,
                    horizon=horizon,
                    forecast_time=forecast_time,
                    target_time=target_time,
                    valid_until=target_time,
                    trend=ForecastDirection.UP if trend_prediction.label == 1 else ForecastDirection.DOWN,
                    target_price=price_prediction.target_price,
                    confidence=trend_prediction.confidence,
                    generated_at=datetime.now(timezone.utc),
                )
            )
        insert_forecast_records(connection, forecasts)
        if count_batch_forecasts(connection, batch_id) != expected_count:
            raise InferenceError(f"Forecast batch {batch_id} is incomplete after retry")
        mark_batch_ready(connection, batch_id)
        persisted_forecasts = load_batch_forecasts(connection, batch_id)
    return batch_id, persisted_forecasts



def _load_trend_model(connection: sqlite3.Connection, model_version: str):
    payload = _load_model_payload(connection, model_version)
    return deserialize_trend_model(payload)



def _load_price_model(connection: sqlite3.Connection, model_version: str):
    payload = _load_model_payload(connection, model_version)
    return deserialize_price_regressor(payload)



def _load_model_payload(connection: sqlite3.Connection, model_version: str) -> dict:
    try:
        artifact = load_model_artifact(model_version)
        payload = artifact.get("model_payload")
        if payload is not None:
            return payload
    except FileNotFoundError:
        pass

    row = connection.execute(
        "SELECT metrics_json FROM model_versions WHERE model_version = ?",
        (model_version,),
    ).fetchone()
    if row is None:
        raise InferenceError(f"Unknown model version: {model_version}")
    metrics = json.loads(row[0])
    payload = metrics.get("model_payload")
    if payload is None:
        raise InferenceError(f"No model payload available for {model_version}")
    return payload



def _latest_symbol_cutoff(rows, symbol: str) -> datetime:
    symbol_rows = [row for row in rows if row.symbol == symbol]
    if not symbol_rows:
        raise InferenceError(f"No dataset rows found for {symbol}")
    return datetime.fromisoformat(symbol_rows[-1].forecast_time)



def _latest_dataset_row_at_or_before(rows, symbol: str, cutoff: datetime):
    symbol_rows = [
        row
        for row in rows
        if row.symbol == symbol and datetime.fromisoformat(row.forecast_time) <= cutoff
    ]
    if not symbol_rows:
        raise InferenceError(f"No dataset rows found for {symbol} at cutoff {cutoff.isoformat()}")
    return symbol_rows[-1]
