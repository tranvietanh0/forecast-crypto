from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from contracts.events import MarketEvent
from contracts.timeframe import timeframe_to_timedelta


FEATURE_SCHEMA_VERSION = "1.0"
FEATURE_NAMES = [
    "return_1",
    "return_3",
    "momentum_3",
    "rolling_mean_return_3",
    "rolling_volatility_3",
    "regime_strength_6",
]


@dataclass(frozen=True)
class FeatureRow:
    symbol: str
    timeframe: str
    horizon: str
    feature_timestamp: str
    forecast_time: str
    source_start_time: str
    target_time: str
    current_price: float
    feature_values: dict[str, float]
    source_event_ids: list[str]
    target_price: float
    future_return: float
    trend_label: int


def _close_prices(window: list[MarketEvent]) -> list[float]:
    return [event.close_price for event in window]


def _safe_return(current_price: float, previous_price: float) -> float:
    if previous_price == 0:
        return 0.0
    return (current_price / previous_price) - 1.0


def _standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return sqrt(variance)


def build_feature_row(
    events: list[MarketEvent],
    current_index: int,
    horizon_steps: int,
    horizon: str,
) -> FeatureRow:
    current_event = events[current_index]
    target_event = events[current_index + horizon_steps]
    return _build_feature_row(
        events,
        current_index,
        horizon,
        target_event.close_time.isoformat(),
        target_event.close_price,
        _safe_return(target_event.close_price, current_event.close_price),
        1 if target_event.close_price > current_event.close_price else 0,
    )



def build_live_feature_row(events: list[MarketEvent], horizon: str) -> FeatureRow:
    current_index = len(events) - 1
    current_event = events[current_index]
    target_time = current_event.close_time + timeframe_to_timedelta(horizon)
    return _build_feature_row(
        events,
        current_index,
        horizon,
        target_time.isoformat(),
        current_event.close_price,
        0.0,
        0,
    )



def _build_feature_row(
    events: list[MarketEvent],
    current_index: int,
    horizon: str,
    target_time: str,
    target_price: float,
    future_return: float,
    trend_label: int,
) -> FeatureRow:
    current_event = events[current_index]
    current_price = current_event.close_price
    previous_prices = _close_prices(events[max(0, current_index - 6): current_index + 1])
    return_1 = _safe_return(current_price, events[current_index - 1].close_price)
    return_3 = _safe_return(current_price, events[current_index - 3].close_price)
    momentum_3 = current_price - events[current_index - 3].close_price
    rolling_returns = [
        _safe_return(previous_prices[index], previous_prices[index - 1])
        for index in range(1, len(previous_prices))
    ]
    rolling_window = rolling_returns[-3:]
    rolling_mean_return_3 = sum(rolling_window) / len(rolling_window) if rolling_window else 0.0
    rolling_volatility_3 = _standard_deviation(rolling_window)
    regime_strength_6 = _safe_return(current_price, previous_prices[0])
    source_events = events[max(0, current_index - 6): current_index + 1]

    return FeatureRow(
        symbol=current_event.symbol,
        timeframe=current_event.timeframe,
        horizon=horizon,
        feature_timestamp=current_event.close_time.isoformat(),
        forecast_time=current_event.close_time.isoformat(),
        source_start_time=source_events[0].open_time.isoformat(),
        target_time=target_time,
        current_price=current_price,
        feature_values={
            "return_1": return_1,
            "return_3": return_3,
            "momentum_3": momentum_3,
            "rolling_mean_return_3": rolling_mean_return_3,
            "rolling_volatility_3": rolling_volatility_3,
            "regime_strength_6": regime_strength_6,
        },
        source_event_ids=[event.event_id for event in source_events],
        target_price=target_price,
        future_return=future_return,
        trend_label=trend_label,
    )
