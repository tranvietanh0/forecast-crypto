from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


SCHEMA_VERSION = "1.0"


class ForecastDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class ContractValidationError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ContractValidationError("datetime values must be timezone-aware")
        return value.astimezone(timezone.utc)

    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ContractValidationError("datetime strings must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class EventContract:
    schema_version: str
    event_id: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, list):
                data[key] = [item.isoformat() if isinstance(item, datetime) else item for item in value]
            elif isinstance(value, dict):
                data[key] = {
                    child_key: child_value.isoformat() if isinstance(child_value, datetime) else child_value
                    for child_key, child_value in value.items()
                }
            elif isinstance(value, ForecastDirection):
                data[key] = value.value
        return data

    @staticmethod
    def new_event_id() -> str:
        return str(uuid.uuid4())


@dataclass(frozen=True)
class MarketEvent(EventContract):
    provider: str
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.close_time <= self.open_time:
            raise ContractValidationError("close_time must be greater than open_time")
        if self.high_price < self.low_price:
            raise ContractValidationError("high_price must be greater than or equal to low_price")
        if not self.low_price <= self.open_price <= self.high_price:
            raise ContractValidationError("open_price must be between low_price and high_price")
        if not self.low_price <= self.close_price <= self.high_price:
            raise ContractValidationError("close_price must be between low_price and high_price")
        if self.volume < 0:
            raise ContractValidationError("volume must be non-negative")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MarketEvent":
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            provider=payload["provider"],
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            open_time=parse_datetime(payload["open_time"]),
            close_time=parse_datetime(payload["close_time"]),
            open_price=float(payload["open_price"]),
            high_price=float(payload["high_price"]),
            low_price=float(payload["low_price"]),
            close_price=float(payload["close_price"]),
            volume=float(payload["volume"]),
            captured_at=parse_datetime(payload["captured_at"]),
        )


@dataclass(frozen=True)
class FeatureSetBuilt(EventContract):
    dataset_version: str
    symbol: str
    horizon: str
    feature_timestamp: datetime
    feature_values: dict[str, float]
    source_event_ids: list[str]
    built_at: datetime

    def __post_init__(self) -> None:
        if not self.feature_values:
            raise ContractValidationError("feature_values must not be empty")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureSetBuilt":
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            dataset_version=payload["dataset_version"],
            symbol=payload["symbol"],
            horizon=payload["horizon"],
            feature_timestamp=parse_datetime(payload["feature_timestamp"]),
            feature_values={key: float(value) for key, value in payload["feature_values"].items()},
            source_event_ids=list(payload["source_event_ids"]),
            built_at=parse_datetime(payload["built_at"]),
        )


@dataclass(frozen=True)
class ModelRegistered(EventContract):
    model_version: str
    model_family: str
    horizons: list[str]
    symbol_scope: list[str]
    dataset_version: str
    metrics: dict[str, float]
    registered_at: datetime

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelRegistered":
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            model_version=payload["model_version"],
            model_family=payload["model_family"],
            horizons=list(payload["horizons"]),
            symbol_scope=list(payload["symbol_scope"]),
            dataset_version=payload["dataset_version"],
            metrics={key: float(value) for key, value in payload["metrics"].items()},
            registered_at=parse_datetime(payload["registered_at"]),
        )


@dataclass(frozen=True)
class ForecastGenerated(EventContract):
    forecast_batch_id: str
    model_version: str
    symbol: str
    timeframe: str
    horizon: str
    forecast_time: datetime
    target_time: datetime
    trend: ForecastDirection
    target_price: float
    confidence: float
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.target_time <= self.forecast_time:
            raise ContractValidationError("target_time must be greater than forecast_time")
        if not 0 <= self.confidence <= 1:
            raise ContractValidationError("confidence must be between 0 and 1")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ForecastGenerated":
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            forecast_batch_id=payload["forecast_batch_id"],
            model_version=payload["model_version"],
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            horizon=payload["horizon"],
            forecast_time=parse_datetime(payload["forecast_time"]),
            target_time=parse_datetime(payload["target_time"]),
            trend=ForecastDirection(payload["trend"]),
            target_price=float(payload["target_price"]),
            confidence=float(payload["confidence"]),
            generated_at=parse_datetime(payload["generated_at"]),
        )


@dataclass(frozen=True)
class NotificationSnapshot(EventContract):
    notification_run_id: str
    forecast_batch_id: str
    delivery_channel: str
    scheduled_for: datetime
    symbols: list[str]
    message_preview: str
    generated_at: datetime

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NotificationSnapshot":
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            notification_run_id=payload["notification_run_id"],
            forecast_batch_id=payload["forecast_batch_id"],
            delivery_channel=payload["delivery_channel"],
            scheduled_for=parse_datetime(payload["scheduled_for"]),
            symbols=list(payload["symbols"]),
            message_preview=payload["message_preview"],
            generated_at=parse_datetime(payload["generated_at"]),
        )
