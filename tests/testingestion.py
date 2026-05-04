from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from contracts.events import MarketEvent, SCHEMA_VERSION
from services.ingestion.ingest import ingest_market_window
from services.ingestion.storage import load_market_events
from tools.migrate import apply_all, connect


class FakeProvider:
    def __init__(self, events_by_symbol: dict[str, list[MarketEvent]]) -> None:
        self.events_by_symbol = events_by_symbol

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MarketEvent]:
        return self.events_by_symbol[symbol]


class FailingProvider(FakeProvider):
    def __init__(self, events_by_symbol: dict[str, list[MarketEvent]], failing_symbol: str) -> None:
        super().__init__(events_by_symbol)
        self.failing_symbol = failing_symbol

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MarketEvent]:
        if symbol == self.failing_symbol:
            raise RuntimeError("provider failure")
        return super().fetch_candles(symbol, timeframe, start_time, end_time)


class IngestionTests(unittest.TestCase):
    def test_ingestion_is_idempotent_and_reports_quality_issues(self) -> None:
        base_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        events = [
            self._market_event("BTCUSDT", base_time, timedelta(hours=2), 100.0, 101.0),
            self._market_event("BTCUSDT", base_time + timedelta(hours=2), timedelta(hours=1), 101.0, 102.0),
            self._market_event("BTCUSDT", base_time + timedelta(hours=1), timedelta(hours=1), 99.0, 100.0),
            self._market_event("BTCUSDT", base_time + timedelta(hours=1), timedelta(hours=1), 99.0, 100.0),
        ]
        provider = FakeProvider({"BTCUSDT": events})

        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'ingestion.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                first_audit = ingest_market_window(
                    connection,
                    provider,
                    ["BTCUSDT"],
                    "1h",
                    base_time,
                    base_time + timedelta(hours=4),
                )["BTCUSDT"]
                second_audit = ingest_market_window(
                    connection,
                    provider,
                    ["BTCUSDT"],
                    "1h",
                    base_time,
                    base_time + timedelta(hours=4),
                )["BTCUSDT"]
                stored_events = load_market_events(connection, "BTCUSDT", "1h")

            self.assertEqual(first_audit.inserted_events, 3)
            self.assertEqual(first_audit.skipped_duplicates, 1)
            self.assertEqual(first_audit.quality_report.duplicate_events, 1)
            self.assertEqual(first_audit.quality_report.missing_candles, 1)
            self.assertEqual(first_audit.quality_report.out_of_order_timestamps, 2)
            self.assertEqual(first_audit.quality_report.provider_drift_events, 1)
            self.assertEqual(second_audit.inserted_events, 0)
            self.assertEqual(second_audit.skipped_duplicates, 4)
            self.assertEqual(len(stored_events), 3)

    def test_multi_symbol_ingestion_rolls_back_when_a_provider_call_fails(self) -> None:
        base_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        events_by_symbol = {
            "BTCUSDT": [self._market_event("BTCUSDT", base_time, timedelta(hours=1), 100.0, 101.0)],
            "ETHUSDT": [self._market_event("ETHUSDT", base_time, timedelta(hours=1), 150.0, 151.0)],
        }
        provider = FailingProvider(events_by_symbol, failing_symbol="ETHUSDT")

        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'rollback.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                with self.assertRaises(RuntimeError):
                    ingest_market_window(
                        connection,
                        provider,
                        ["BTCUSDT", "ETHUSDT"],
                        "1h",
                        base_time,
                        base_time + timedelta(hours=1),
                    )
                stored_events = load_market_events(connection, "BTCUSDT", "1h")

            self.assertEqual(stored_events, [])

    def _market_event(
        self,
        symbol: str,
        open_time: datetime,
        span: timedelta,
        open_price: float,
        close_price: float,
    ) -> MarketEvent:
        high_price = max(open_price, close_price) + 1.0
        low_price = min(open_price, close_price) - 1.0
        open_time_ms = int(open_time.timestamp() * 1000)
        return MarketEvent(
            schema_version=SCHEMA_VERSION,
            event_id=f"binance:{symbol}:1h:{open_time_ms}",
            provider="binance",
            symbol=symbol,
            timeframe="1h",
            open_time=open_time,
            close_time=open_time + span,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=10.0,
            captured_at=open_time + timedelta(minutes=1),
        )
