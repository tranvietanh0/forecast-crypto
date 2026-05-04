from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import os
import sqlite3

from contracts.config import load_config
from contracts.timeframe import horizon_to_steps, timeframe_to_timedelta
from services.ingestion.binance import BinanceProvider, MarketDataProvider
from services.ingestion.quality import IngestionAudit, analyze_market_events
from services.ingestion.storage import insert_market_events
from services.pipeline.datasets import MIN_HISTORY_EVENTS
from services.pipeline.train import run_phase_two_training
from services.inference.generate import run_live_inference_batch


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "defaults.json"
DEFAULT_TIMEFRAME = "1h"
MIN_TRAINING_ROWS = 96


class IngestionError(RuntimeError):
    pass



def ingest_market_window(
    connection: sqlite3.Connection,
    provider: MarketDataProvider,
    symbols: list[str],
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
) -> dict[str, IngestionAudit]:
    if end_time <= start_time:
        raise IngestionError("end_time must be greater than start_time")

    audits: dict[str, IngestionAudit] = {}
    with connection:
        for symbol in symbols:
            events = provider.fetch_candles(symbol, timeframe, start_time, end_time)
            quality_report = analyze_market_events(events)
            inserted, skipped = insert_market_events(connection, events)
            audits[symbol] = IngestionAudit(
                inserted_events=inserted,
                skipped_duplicates=skipped,
                quality_report=quality_report,
            )
    return audits



def sync_live_forecasts(
    connection: sqlite3.Connection,
    database_url: str,
    timeframe: str = DEFAULT_TIMEFRAME,
    horizons: list[str] | None = None,
    requested_symbols: list[str] | None = None,
    provider: MarketDataProvider | None = None,
    current_time: datetime | None = None,
) -> dict:
    runtime_end_time = align_to_completed_candle(current_time or datetime.now(timezone.utc), timeframe)
    config = _load_runtime_config(database_url)
    active_horizons = horizons or config.forecast_horizons
    active_symbols = _resolve_symbols(config.coin_universe, requested_symbols)
    market_provider = provider or BinanceProvider(config.providers["market"])
    lookback_start_time = _calculate_lookback_start(runtime_end_time, timeframe, active_horizons)

    purge_future_demo_data(connection, runtime_end_time)
    audits = ingest_market_window(
        connection,
        market_provider,
        active_symbols,
        timeframe,
        lookback_start_time,
        runtime_end_time,
    )

    generated_batches: dict[str, dict] = {}
    for horizon in active_horizons:
        artifacts = run_phase_two_training(connection, active_symbols, timeframe, horizon)
        batch_id, forecasts = run_live_inference_batch(
            connection,
            artifacts.dataset_bundle.symbols,
            timeframe,
            horizon,
        )
        generated_batches[horizon] = {
            "forecast_batch_id": batch_id,
            "symbols": artifacts.dataset_bundle.symbols,
            "forecast_count": len(forecasts),
        }

    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": timeframe,
        "lookback_start_time": lookback_start_time.isoformat(),
        "lookback_end_time": runtime_end_time.isoformat(),
        "symbols": active_symbols,
        "horizons": active_horizons,
        "audits": {
            symbol: {
                "inserted_events": audit.inserted_events,
                "skipped_duplicates": audit.skipped_duplicates,
                "missing_candles": audit.quality_report.missing_candles,
                "duplicate_events": audit.quality_report.duplicate_events,
                "out_of_order_timestamps": audit.quality_report.out_of_order_timestamps,
                "provider_drift_events": audit.quality_report.provider_drift_events,
            }
            for symbol, audit in audits.items()
        },
        "batches": generated_batches,
    }



def _load_runtime_config(database_url: str):
    env = dict(os.environ)
    env.setdefault("DATABASE_URL", database_url)
    return load_config(DEFAULT_CONFIG_PATH, env=env)



def _resolve_symbols(config_symbols: list[str], requested_symbols: list[str] | None) -> list[str]:
    if requested_symbols:
        return list(dict.fromkeys(requested_symbols))
    return list(dict.fromkeys(config_symbols))



def _calculate_lookback_start(end_time: datetime, timeframe: str, horizons: Iterable[str]) -> datetime:
    timeframe_delta = timeframe_to_timedelta(timeframe)
    max_horizon_steps = max(horizon_to_steps(timeframe, horizon) for horizon in horizons)
    total_events = MIN_HISTORY_EVENTS + max_horizon_steps + MIN_TRAINING_ROWS
    return end_time - (timeframe_delta * total_events)



def align_to_completed_candle(current_time: datetime, timeframe: str) -> datetime:
    current_utc = current_time.astimezone(timezone.utc).replace(second=0, microsecond=0)
    step_seconds = int(timeframe_to_timedelta(timeframe).total_seconds())
    aligned_epoch = int(current_utc.timestamp())
    aligned_epoch -= aligned_epoch % step_seconds
    return datetime.fromtimestamp(aligned_epoch, tz=timezone.utc)



def purge_future_demo_data(connection: sqlite3.Connection, cutoff_time: datetime) -> None:
    cutoff_iso = cutoff_time.isoformat()
    future_dataset_versions = [
        row[0]
        for row in connection.execute(
            "SELECT dataset_version FROM dataset_versions WHERE source_end_time > ?",
            (cutoff_iso,),
        ).fetchall()
    ]

    future_model_versions = [
        row[0]
        for row in connection.execute(
            "SELECT model_version FROM model_versions WHERE registered_at > ?",
            (cutoff_iso,),
        ).fetchall()
    ]
    if future_dataset_versions:
        future_model_versions.extend(
            row[0]
            for row in connection.execute(
                "SELECT model_version FROM model_versions WHERE dataset_version IN ({})".format(_placeholders(future_dataset_versions)),
                tuple(future_dataset_versions),
            ).fetchall()
        )
    future_model_versions = list(dict.fromkeys(future_model_versions))

    future_batch_ids = [
        row[0]
        for row in connection.execute(
            "SELECT forecast_batch_id FROM forecast_batches WHERE forecast_time > ?",
            (cutoff_iso,),
        ).fetchall()
    ]
    if future_model_versions:
        future_batch_ids.extend(
            row[0]
            for row in connection.execute(
                "SELECT forecast_batch_id FROM forecast_batches WHERE model_version IN ({})".format(_placeholders(future_model_versions)),
                tuple(future_model_versions),
            ).fetchall()
        )
    future_batch_ids = list(dict.fromkeys(future_batch_ids))

    future_forecast_ids = [
        row[0]
        for row in connection.execute(
            "SELECT forecast_id FROM forecasts WHERE forecast_time > ?",
            (cutoff_iso,),
        ).fetchall()
    ]
    if future_batch_ids:
        future_forecast_ids.extend(
            row[0]
            for row in connection.execute(
                "SELECT forecast_id FROM forecasts WHERE forecast_batch_id IN ({})".format(_placeholders(future_batch_ids)),
                tuple(future_batch_ids),
            ).fetchall()
        )
    future_forecast_ids = list(dict.fromkeys(future_forecast_ids))

    with connection:
        if future_forecast_ids:
            connection.execute(
                "DELETE FROM realized_outcomes WHERE forecast_id IN ({})".format(_placeholders(future_forecast_ids)),
                tuple(future_forecast_ids),
            )
        if future_batch_ids:
            connection.execute(
                "DELETE FROM notification_runs WHERE forecast_batch_id IN ({})".format(_placeholders(future_batch_ids)),
                tuple(future_batch_ids),
            )
            connection.execute(
                "DELETE FROM forecasts WHERE forecast_batch_id IN ({})".format(_placeholders(future_batch_ids)),
                tuple(future_batch_ids),
            )
            connection.execute(
                "DELETE FROM forecast_batches WHERE forecast_batch_id IN ({})".format(_placeholders(future_batch_ids)),
                tuple(future_batch_ids),
            )
        if future_model_versions:
            connection.execute(
                "DELETE FROM model_versions WHERE model_version IN ({})".format(_placeholders(future_model_versions)),
                tuple(future_model_versions),
            )
        if future_dataset_versions:
            connection.execute(
                "DELETE FROM dataset_versions WHERE dataset_version IN ({})".format(_placeholders(future_dataset_versions)),
                tuple(future_dataset_versions),
            )
        connection.execute(
            "DELETE FROM raw_market_events WHERE open_time > ? OR close_time > ?",
            (cutoff_iso, cutoff_iso),
        )



def _placeholders(values: list[str]) -> str:
    if not values:
        raise IngestionError("placeholders requested for an empty value list")
    return ", ".join("?" for _ in values)
