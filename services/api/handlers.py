from __future__ import annotations

import sqlite3

from services.inference.storage import load_batch_detail, load_batch_forecasts, load_forecast_history, load_latest_ready_batch_id


class ApiError(RuntimeError):
    pass


MAX_HISTORY_LIMIT = 200



def get_latest_forecasts(
    connection: sqlite3.Connection,
    timeframe: str,
    horizon: str,
    watchlist: list[str] | None = None,
) -> dict:
    batch_id = load_latest_ready_batch_id(connection, timeframe, horizon, watchlist)
    if batch_id is None:
        raise ApiError("No ready forecast batch found")

    forecasts = load_batch_forecasts(connection, batch_id)
    if watchlist:
        watchlist_set = set(watchlist)
        forecasts = [forecast for forecast in forecasts if forecast.symbol in watchlist_set]
    return {
        "forecast_batch_id": batch_id,
        "timeframe": timeframe,
        "horizon": horizon,
        "forecasts": [forecast.to_dict() for forecast in forecasts],
    }



def get_forecast_history(
    connection: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    horizon: str,
    limit: int = 20,
) -> dict:
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if limit > MAX_HISTORY_LIMIT:
        raise ValueError(f"limit must be less than or equal to {MAX_HISTORY_LIMIT}")
    history = load_forecast_history(connection, symbol, timeframe, horizon, limit)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon": horizon,
        "history": [forecast.to_dict() for forecast in history],
    }



def get_forecast_batch_detail(connection: sqlite3.Connection, batch_id: str) -> dict:
    detail = load_batch_detail(connection, batch_id)
    if detail is None:
        raise ApiError(f"Unknown forecast batch: {batch_id}")
    forecasts = load_batch_forecasts(connection, batch_id)
    return {
        **detail,
        "forecasts": [forecast.to_dict() for forecast in forecasts],
    }
