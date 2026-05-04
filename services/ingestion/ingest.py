from __future__ import annotations

from datetime import datetime
import sqlite3

from services.ingestion.binance import MarketDataProvider
from services.ingestion.quality import IngestionAudit, analyze_market_events
from services.ingestion.storage import insert_market_events


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
