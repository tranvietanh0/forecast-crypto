from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from contracts.config import ProviderConfig
from services.ingestion.binance import BinanceProvider


class PaginatedBinanceProvider(BinanceProvider):
    def __init__(self, provider_config: ProviderConfig, pages: list[list[list[object]]]) -> None:
        super().__init__(provider_config)
        self.pages = pages
        self.calls = 0

    def _fetch_page(
        self,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[list[object]]:
        page = self.pages[self.calls]
        self.calls += 1
        return page


class BinanceProviderTests(unittest.TestCase):
    def test_fetch_candles_filters_overlap_and_end_boundary_rows(self) -> None:
        provider = PaginatedBinanceProvider(
            ProviderConfig(name="binance", base_url="https://api.binance.com", candles_path="/api/v3/klines"),
            pages=[
                self._build_page(0, 1000),
                self._build_page(999, 4),
            ],
        )
        start_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=1003)

        candles = provider.fetch_candles("BTCUSDT", "1h", start_time, end_time)

        self.assertEqual(len(candles), 1003)
        self.assertEqual(len({candle.event_id for candle in candles}), 1003)
        self.assertTrue(all(start_time <= candle.open_time < end_time for candle in candles))

    def test_fetch_candles_paginates_beyond_provider_page_size(self) -> None:
        provider = PaginatedBinanceProvider(
            ProviderConfig(name="binance", base_url="https://api.binance.com", candles_path="/api/v3/klines"),
            pages=[self._build_page(0, 1000), self._build_page(1000, 2)],
        )

        candles = provider.fetch_candles(
            "BTCUSDT",
            "1h",
            datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(candles), 1002)
        self.assertEqual(provider.calls, 2)
        first_open_time_ms = int(datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(candles[0].event_id, f"binance:BTCUSDT:1h:{first_open_time_ms}")
        last_open_time_ms = int((datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc) + timedelta(hours=1001)).timestamp() * 1000)
        self.assertEqual(candles[-1].event_id, f"binance:BTCUSDT:1h:{last_open_time_ms}")

    def _build_page(self, start_index: int, count: int) -> list[list[object]]:
        base_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        candles: list[list[object]] = []
        for index in range(start_index, start_index + count):
            open_time = base_time + timedelta(hours=index)
            close_time = open_time + timedelta(hours=1)
            open_time_ms = int(open_time.timestamp() * 1000)
            close_time_ms = int(close_time.timestamp() * 1000)
            candles.append(
                [
                    open_time_ms,
                    "100.0",
                    "101.0",
                    "99.0",
                    "100.5",
                    "50.0",
                    close_time_ms,
                ]
            )
        return candles
