from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from contracts.events import ForecastGenerated


BATCH_STATUS_PENDING = "pending"
BATCH_STATUS_READY = "ready"


class BatchStorageError(RuntimeError):
    pass



def forecast_batch_id(batch_key: str) -> str:
    return f"batch:{batch_key}"



def forecast_record_id(batch_id: str, symbol: str, timeframe: str, horizon: str) -> str:
    return f"forecast:{batch_id}:{symbol}:{timeframe}:{horizon}"



def ensure_forecast_batch(
    connection: sqlite3.Connection,
    batch_key: str,
    model_version: str,
    timeframe: str,
    horizon: str,
    symbols: list[str],
    forecast_time: datetime,
) -> tuple[str, bool]:
    batch_id = forecast_batch_id(batch_key)
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO forecast_batches(
            forecast_batch_id,
            model_version,
            timeframe,
            horizon,
            forecast_time,
            coin_universe_json,
            batch_status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            model_version,
            timeframe,
            horizon,
            forecast_time.isoformat(),
            json.dumps(symbols),
            BATCH_STATUS_PENDING,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return batch_id, cursor.rowcount == 1



def insert_forecast_records(
    connection: sqlite3.Connection,
    forecasts: list[ForecastGenerated],
) -> int:
    inserted = 0
    for forecast in forecasts:
        payload = forecast.to_dict()
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO forecasts(
                forecast_id,
                forecast_batch_id,
                model_version,
                symbol,
                timeframe,
                horizon,
                forecast_time,
                target_time,
                trend,
                target_price,
                confidence,
                generated_at,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forecast_record_id(
                    forecast.forecast_batch_id,
                    forecast.symbol,
                    forecast.timeframe,
                    forecast.horizon,
                ),
                forecast.forecast_batch_id,
                forecast.model_version,
                forecast.symbol,
                forecast.timeframe,
                forecast.horizon,
                forecast.forecast_time.isoformat(),
                forecast.target_time.isoformat(),
                forecast.trend.value,
                forecast.target_price,
                forecast.confidence,
                forecast.generated_at.isoformat(),
                json.dumps(payload),
            ),
        )
        inserted += 1 if cursor.rowcount == 1 else 0
    return inserted



def count_batch_forecasts(connection: sqlite3.Connection, batch_id: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM forecasts WHERE forecast_batch_id = ?",
        (batch_id,),
    ).fetchone()
    return int(row[0])



def mark_batch_ready(connection: sqlite3.Connection, batch_id: str) -> None:
    cursor = connection.execute(
        "UPDATE forecast_batches SET batch_status = ? WHERE forecast_batch_id = ?",
        (BATCH_STATUS_READY, batch_id),
    )
    if cursor.rowcount != 1:
        raise BatchStorageError(f"Unknown forecast batch: {batch_id}")



def load_batch_forecasts(connection: sqlite3.Connection, batch_id: str) -> list[ForecastGenerated]:
    rows = connection.execute(
        "SELECT payload_json FROM forecasts WHERE forecast_batch_id = ? ORDER BY symbol ASC",
        (batch_id,),
    ).fetchall()
    return [ForecastGenerated.from_dict(json.loads(row[0])) for row in rows]



def load_batch_status(connection: sqlite3.Connection, batch_id: str) -> str | None:
    row = connection.execute(
        "SELECT batch_status FROM forecast_batches WHERE forecast_batch_id = ?",
        (batch_id,),
    ).fetchone()
    return row[0] if row else None



def load_latest_ready_batch_id(
    connection: sqlite3.Connection,
    timeframe: str,
    horizon: str,
    watchlist: list[str] | None = None,
) -> str | None:
    rows = connection.execute(
        """
        SELECT forecast_batches.forecast_batch_id, forecast_batches.coin_universe_json
        FROM forecast_batches
        WHERE forecast_batches.timeframe = ? AND forecast_batches.horizon = ? AND forecast_batches.batch_status = ?
        ORDER BY forecast_batches.forecast_time DESC, forecast_batches.created_at DESC, forecast_batches.forecast_batch_id DESC
        """,
        (timeframe, horizon, BATCH_STATUS_READY),
    ).fetchall()
    requested_symbols = set(watchlist or [])
    now_iso = datetime.now(timezone.utc).isoformat()
    for batch_id, coin_universe_json in rows:
        batch_symbols = set(json.loads(coin_universe_json))
        if requested_symbols and not requested_symbols.issubset(batch_symbols):
            continue
        forecasts = load_batch_forecasts(connection, batch_id)
        if not forecasts:
            continue
        relevant_forecasts = [
            forecast for forecast in forecasts if not requested_symbols or forecast.symbol in requested_symbols
        ]
        if not relevant_forecasts:
            continue
        if any(forecast.valid_until.isoformat() < now_iso for forecast in relevant_forecasts):
            continue
        return batch_id
    return None



def load_forecast_history(
    connection: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    horizon: str,
    limit: int = 20,
) -> list[ForecastGenerated]:
    rows = connection.execute(
        """
        SELECT forecasts.payload_json
        FROM forecasts
        JOIN forecast_batches ON forecast_batches.forecast_batch_id = forecasts.forecast_batch_id
        WHERE forecasts.symbol = ? AND forecasts.timeframe = ? AND forecasts.horizon = ? AND forecast_batches.batch_status = ?
        ORDER BY forecasts.forecast_time DESC
        LIMIT ?
        """,
        (symbol, timeframe, horizon, BATCH_STATUS_READY, limit),
    ).fetchall()
    return [ForecastGenerated.from_dict(json.loads(row[0])) for row in rows]



def load_batch_detail(connection: sqlite3.Connection, batch_id: str) -> dict | None:
    row = connection.execute(
        """
        SELECT forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at
        FROM forecast_batches
        WHERE forecast_batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "forecast_batch_id": row[0],
        "model_version": row[1],
        "timeframe": row[2],
        "horizon": row[3],
        "forecast_time": row[4],
        "coin_universe": json.loads(row[5]),
        "batch_status": row[6],
        "created_at": row[7],
    }
