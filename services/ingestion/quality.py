from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from contracts.events import MarketEvent
from contracts.timeframe import timeframe_to_timedelta


@dataclass(frozen=True)
class DataQualityReport:
    total_events: int
    duplicate_events: int
    missing_candles: int
    out_of_order_timestamps: int
    provider_drift_events: int


@dataclass(frozen=True)
class IngestionAudit:
    inserted_events: int
    skipped_duplicates: int
    quality_report: DataQualityReport


def analyze_market_events(events: list[MarketEvent]) -> DataQualityReport:
    if not events:
        return DataQualityReport(
            total_events=0,
            duplicate_events=0,
            missing_candles=0,
            out_of_order_timestamps=0,
            provider_drift_events=0,
        )

    expected_step = timeframe_to_timedelta(events[0].timeframe)
    seen_event_ids: set[str] = set()
    duplicate_events = 0
    out_of_order_timestamps = 0
    provider_drift_events = 0
    missing_candles = 0

    previous_open_time = events[0].open_time
    for index, event in enumerate(events):
        if event.event_id in seen_event_ids:
            duplicate_events += 1
        seen_event_ids.add(event.event_id)

        candle_span = event.close_time - event.open_time
        if candle_span <= timedelta() or candle_span > expected_step:
            provider_drift_events += 1

        if index == 0:
            continue

        if event.open_time <= previous_open_time:
            out_of_order_timestamps += 1
        else:
            gap = event.open_time - previous_open_time
            if gap > expected_step:
                missing_candles += int(gap / expected_step) - 1
        previous_open_time = event.open_time

    return DataQualityReport(
        total_events=len(events),
        duplicate_events=duplicate_events,
        missing_candles=missing_candles,
        out_of_order_timestamps=out_of_order_timestamps,
        provider_drift_events=provider_drift_events,
    )
