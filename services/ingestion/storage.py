from __future__ import annotations

from contracts.events import MarketEvent
import json
import sqlite3


def insert_market_events(
    connection: sqlite3.Connection,
    events: list[MarketEvent],
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for event in events:
        payload = event.to_dict()
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO raw_market_events(
                event_id,
                schema_version,
                provider,
                symbol,
                timeframe,
                open_time,
                close_time,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                captured_at,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.schema_version,
                event.provider,
                event.symbol,
                event.timeframe,
                event.open_time.isoformat(),
                event.close_time.isoformat(),
                event.open_price,
                event.high_price,
                event.low_price,
                event.close_price,
                event.volume,
                event.captured_at.isoformat(),
                json.dumps(payload),
            ),
        )
        if cursor.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def load_market_events(
    connection: sqlite3.Connection,
    symbol: str,
    timeframe: str,
) -> list[MarketEvent]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM raw_market_events
        WHERE symbol = ? AND timeframe = ?
        ORDER BY open_time ASC
        """,
        (symbol, timeframe),
    ).fetchall()
    return [MarketEvent.from_dict(json.loads(row[0])) for row in rows]
