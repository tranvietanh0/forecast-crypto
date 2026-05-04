from __future__ import annotations

from datetime import datetime, timezone
import unittest

from contracts.events import (
    ContractValidationError,
    FeatureSetBuilt,
    ForecastDirection,
    ForecastGenerated,
    MarketEvent,
    ModelRegistered,
    NotificationSnapshot,
    SCHEMA_VERSION,
)


class ContractRoundTripTests(unittest.TestCase):
    def test_market_event_round_trip(self) -> None:
        market_event = MarketEvent(
            schema_version=SCHEMA_VERSION,
            event_id=MarketEvent.new_event_id(),
            provider="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
            open_price=95000.0,
            high_price=96000.0,
            low_price=94800.0,
            close_price=95500.0,
            volume=120.5,
            captured_at=datetime(2026, 5, 1, 1, 1, tzinfo=timezone.utc),
        )

        restored = MarketEvent.from_dict(market_event.to_dict())
        self.assertEqual(restored, market_event)

    def test_market_event_rejects_invalid_candle_ranges(self) -> None:
        with self.assertRaises(ContractValidationError):
            MarketEvent(
                schema_version=SCHEMA_VERSION,
                event_id=MarketEvent.new_event_id(),
                provider="binance",
                symbol="BTCUSDT",
                timeframe="1h",
                open_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                close_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                open_price=97000.0,
                high_price=96000.0,
                low_price=94800.0,
                close_price=94000.0,
                volume=120.5,
                captured_at=datetime(2026, 5, 1, 1, 1, tzinfo=timezone.utc),
            )

    def test_forecast_generated_rejects_invalid_target_time(self) -> None:
        with self.assertRaises(ContractValidationError):
            ForecastGenerated(
                schema_version=SCHEMA_VERSION,
                event_id=ForecastGenerated.new_event_id(),
                forecast_batch_id="batch-1",
                model_version="model-v1",
                symbol="BTCUSDT",
                timeframe="1h",
                horizon="4h",
                forecast_time=datetime(2026, 5, 1, 5, 0, tzinfo=timezone.utc),
                target_time=datetime(2026, 5, 1, 5, 0, tzinfo=timezone.utc),
                trend=ForecastDirection.UP,
                target_price=97250.0,
                confidence=0.78,
                generated_at=datetime(2026, 5, 1, 1, 11, tzinfo=timezone.utc),
            )

    def test_feature_model_forecast_and_notification_round_trip(self) -> None:
        feature_set = FeatureSetBuilt(
            schema_version=SCHEMA_VERSION,
            event_id=FeatureSetBuilt.new_event_id(),
            dataset_version="dataset-v1",
            symbol="BTCUSDT",
            horizon="4h",
            feature_timestamp=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
            feature_values={"rsi_14": 59.2, "volatility_24h": 0.032},
            source_event_ids=["event-1", "event-2"],
            built_at=datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc),
        )
        model_registered = ModelRegistered(
            schema_version=SCHEMA_VERSION,
            event_id=ModelRegistered.new_event_id(),
            model_version="model-v1",
            model_family="xgboost",
            horizons=["4h", "24h"],
            symbol_scope=["BTCUSDT", "ETHUSDT"],
            dataset_version="dataset-v1",
            metrics={"direction_accuracy": 0.61, "mape": 0.045},
            registered_at=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
        )
        forecast_generated = ForecastGenerated(
            schema_version=SCHEMA_VERSION,
            event_id=ForecastGenerated.new_event_id(),
            forecast_batch_id="batch-1",
            model_version="model-v1",
            symbol="BTCUSDT",
            timeframe="1h",
            horizon="4h",
            forecast_time=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
            target_time=datetime(2026, 5, 1, 5, 0, tzinfo=timezone.utc),
            trend=ForecastDirection.UP,
            target_price=97250.0,
            confidence=0.78,
            generated_at=datetime(2026, 5, 1, 1, 11, tzinfo=timezone.utc),
        )
        notification_snapshot = NotificationSnapshot(
            schema_version=SCHEMA_VERSION,
            event_id=NotificationSnapshot.new_event_id(),
            notification_run_id="notification-1",
            forecast_batch_id="batch-1",
            delivery_channel="telegram",
            scheduled_for=datetime(2026, 5, 1, 1, 15, tzinfo=timezone.utc),
            symbols=["BTCUSDT", "ETHUSDT"],
            message_preview="BTCUSDT: up to 97250.0",
            generated_at=datetime(2026, 5, 1, 1, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(FeatureSetBuilt.from_dict(feature_set.to_dict()), feature_set)
        self.assertEqual(ModelRegistered.from_dict(model_registered.to_dict()), model_registered)
        self.assertEqual(ForecastGenerated.from_dict(forecast_generated.to_dict()), forecast_generated)
        self.assertEqual(NotificationSnapshot.from_dict(notification_snapshot.to_dict()), notification_snapshot)
