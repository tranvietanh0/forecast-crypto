from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen
import json

from contracts.config import ProviderConfig
from contracts.events import MarketEvent, SCHEMA_VERSION


class ProviderResponseError(RuntimeError):
    pass


class MarketDataProvider(Protocol):
    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MarketEvent]:
        ...


MAX_PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 15



def _to_milliseconds(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)



def _from_milliseconds(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)



def _deterministic_event_id(provider: str, symbol: str, timeframe: str, open_time_ms: int) -> str:
    return f"{provider}:{symbol}:{timeframe}:{open_time_ms}"


class BinanceProvider:
    def __init__(self, provider_config: ProviderConfig) -> None:
        self.provider_config = provider_config

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MarketEvent]:
        requested_start_ms = _to_milliseconds(start_time)
        requested_end_ms = _to_milliseconds(end_time)
        page_start_ms = requested_start_ms
        candles: list[list[Any]] = []

        while page_start_ms < requested_end_ms:
            payload = self._fetch_page(symbol, timeframe, page_start_ms, requested_end_ms)
            if not payload:
                break
            candles.extend(payload)
            if len(payload) < MAX_PAGE_SIZE:
                break
            last_open_time_ms = int(payload[-1][0])
            if last_open_time_ms <= page_start_ms:
                raise ProviderResponseError("Provider pagination did not advance")
            page_start_ms = last_open_time_ms + 1

        normalized = [normalize_binance_candle(symbol, timeframe, candle) for candle in candles]
        unique_events: dict[str, MarketEvent] = {}
        for event in normalized:
            if event.open_time < start_time or event.open_time >= end_time:
                continue
            unique_events.setdefault(event.event_id, event)
        return sorted(unique_events.values(), key=lambda event: event.open_time)

    def _fetch_page(
        self,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[list[Any]]:
        query = urlencode(
            {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": MAX_PAGE_SIZE,
            }
        )
        url = (
            f"{self.provider_config.base_url}"
            f"{self.provider_config.candles_path}?{query}"
        )
        with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ProviderResponseError(f"Provider returned HTTP {status}")
            payload = json.loads(response.read().decode("utf-8"))

        if isinstance(payload, dict):
            message = payload.get("msg") or payload.get("message") or "Unknown provider error"
            raise ProviderResponseError(f"Provider returned error payload: {message}")
        if not isinstance(payload, list) or any(not isinstance(item, list) for item in payload):
            raise ProviderResponseError("Provider returned an unexpected candle payload shape")
        return payload



def normalize_binance_candle(symbol: str, timeframe: str, candle: list[Any]) -> MarketEvent:
    open_time_ms = int(candle[0])
    close_time_ms = int(candle[6])
    return MarketEvent(
        schema_version=SCHEMA_VERSION,
        event_id=_deterministic_event_id("binance", symbol, timeframe, open_time_ms),
        provider="binance",
        symbol=symbol,
        timeframe=timeframe,
        open_time=_from_milliseconds(open_time_ms),
        close_time=_from_milliseconds(close_time_ms),
        open_price=float(candle[1]),
        high_price=float(candle[2]),
        low_price=float(candle[3]),
        close_price=float(candle[4]),
        volume=float(candle[5]),
        captured_at=datetime.now(timezone.utc),
    )
