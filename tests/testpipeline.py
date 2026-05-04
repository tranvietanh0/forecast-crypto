from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from contracts.events import MarketEvent, SCHEMA_VERSION
from contracts.timeframe import TimeframeError, timeframe_to_timedelta
from services.ingestion.storage import insert_market_events
import services.pipeline.backtest as backtest_module
import services.pipeline.datasets as datasets_module
import services.pipeline.registry as registry_module
from services.pipeline.train import run_phase_two_training
from tools.migrate import apply_all, connect


class PipelineTests(unittest.TestCase):
    def test_dataset_is_reproducible_and_training_registers_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'pipeline.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))

                dataset_one = datasets_module.build_dataset_bundle(
                    connection,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                )
                dataset_two = datasets_module.build_dataset_bundle(
                    connection,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                )
                dataset_three = datasets_module.build_dataset_bundle(
                    connection,
                    ["ETHUSDT", "BTCUSDT"],
                    "1h",
                    "4h",
                )
                self.assertEqual(dataset_one.dataset_version, dataset_two.dataset_version)
                self.assertEqual(dataset_one.dataset_version, dataset_three.dataset_version)
                self.assertGreater(len(dataset_one.rows), 0)
                self.assertTrue(
                    all(row.feature_timestamp <= row.target_time for row in dataset_one.rows)
                )

                artifacts = run_phase_two_training(
                    connection,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                )
                dataset_artifact_path = artifacts_dir / f"{artifacts.dataset_bundle.dataset_version}.json"
                trend_artifact_path = artifacts_dir / f"{artifacts.trend_registration.model_version}.json"
                backtest_artifact_path = artifacts_dir / artifacts.backtest_artifact_name
                dataset_artifact_before_retry = dataset_artifact_path.read_text(encoding="utf-8")
                trend_artifact_before_retry = trend_artifact_path.read_text(encoding="utf-8")
                backtest_artifact_before_retry = backtest_artifact_path.read_text(encoding="utf-8")
                dataset_artifact_path.write_text('{"stale": true}', encoding="utf-8")
                trend_artifact_path.write_text('{"stale": true}', encoding="utf-8")
                backtest_artifact_path.write_text('{"stale": true}', encoding="utf-8")
                retry_artifacts = run_phase_two_training(
                    connection,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                )

                dataset_rows = connection.execute(
                    "SELECT dataset_version FROM dataset_versions"
                ).fetchall()
                model_rows = connection.execute(
                    "SELECT model_version, model_family FROM model_versions ORDER BY model_family"
                ).fetchall()

            self.assertEqual(dataset_rows, [(artifacts.dataset_bundle.dataset_version,)])
            self.assertEqual(retry_artifacts.dataset_bundle.dataset_version, artifacts.dataset_bundle.dataset_version)
            self.assertEqual(retry_artifacts.backtest_artifact_name, artifacts.backtest_artifact_name)
            self.assertEqual(dataset_artifact_before_retry, dataset_artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(trend_artifact_before_retry, trend_artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(backtest_artifact_before_retry, backtest_artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(len(model_rows), 2)
            self.assertEqual(set(artifacts.backtest_report.per_symbol), {"BTCUSDT", "ETHUSDT"})
            self.assertGreater(artifacts.backtest_report.aggregate.sample_count, 0)
            self.assertTrue((artifacts_dir / f"{artifacts.dataset_bundle.dataset_version}.json").exists())
            self.assertTrue((artifacts_dir / artifacts.backtest_artifact_name).exists())
            self.assertTrue((artifacts_dir / f"{artifacts.trend_registration.model_version}.json").exists())
            self.assertTrue((artifacts_dir / f"{artifacts.price_registration.model_version}.json").exists())

    def test_training_handles_one_class_history_and_tracks_only_usable_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'single-class.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=True))
                insert_market_events(connection, self._build_short_history("ETHUSDT", 150.0))
                artifacts = run_phase_two_training(
                    connection,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                )

            self.assertEqual(artifacts.dataset_bundle.symbols, ["BTCUSDT"])
            self.assertEqual(artifacts.trend_registration.symbols, ["BTCUSDT"])
            self.assertEqual(artifacts.price_registration.symbols, ["BTCUSDT"])
            self.assertGreater(artifacts.backtest_report.aggregate.sample_count, 0)

    def test_zero_timeframe_is_rejected(self) -> None:
        with self.assertRaises(TimeframeError):
            timeframe_to_timedelta("0h")

    def _build_market_events(self, symbol: str, base_price: float, trending: bool) -> list[MarketEvent]:
        base_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        prices = []
        for index in range(32):
            if trending:
                prices.append(base_price + index * 0.9)
            else:
                wave = [0.0, 2.5, -1.0, 3.0, -2.0, 1.5, -0.5, 2.0][index % 8]
                prices.append(base_price + index * 0.35 + wave)

        events: list[MarketEvent] = []
        for index in range(1, len(prices)):
            open_time = base_time + timedelta(hours=index - 1)
            open_price = prices[index - 1]
            close_price = prices[index]
            high_price = max(open_price, close_price) + 0.8
            low_price = min(open_price, close_price) - 0.8
            open_time_ms = int(open_time.timestamp() * 1000)
            events.append(
                MarketEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=f"binance:{symbol}:1h:{open_time_ms}",
                    provider="binance",
                    symbol=symbol,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=100 + index,
                    captured_at=open_time + timedelta(hours=1, minutes=1),
                )
            )
        return events

    def _build_short_history(self, symbol: str, base_price: float) -> list[MarketEvent]:
        base_time = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        events: list[MarketEvent] = []
        for index in range(3):
            open_time = base_time + timedelta(hours=index)
            open_time_ms = int(open_time.timestamp() * 1000)
            open_price = base_price + index
            close_price = open_price + 0.5
            events.append(
                MarketEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=f"binance:{symbol}:1h:{open_time_ms}",
                    provider="binance",
                    symbol=symbol,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open_price=open_price,
                    high_price=close_price + 0.5,
                    low_price=open_price - 0.5,
                    close_price=close_price,
                    volume=10 + index,
                    captured_at=open_time + timedelta(hours=1, minutes=1),
                )
            )
        return events
