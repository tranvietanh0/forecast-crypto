from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from contracts.events import ForecastDirection, ForecastGenerated, MarketEvent, SCHEMA_VERSION
from services.inference.generate import build_batch_key, run_inference_batch
from services.inference.storage import ensure_forecast_batch, insert_forecast_records, load_batch_forecasts
from services.pipeline.train import run_phase_two_training
import services.pipeline.backtest as backtest_module
import services.pipeline.datasets as datasets_module
import services.pipeline.registry as registry_module
from tests.testpipeline import PipelineTests
from tools.migrate import apply_all, connect


class InferenceTests(PipelineTests):
    def test_inference_batch_is_idempotent_and_persists_ready_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'inference.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

                batch_id, forecasts = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                retry_batch_id, retry_forecasts = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                stored_forecasts = load_batch_forecasts(connection, batch_id)
                batch_row = connection.execute(
                    "SELECT batch_status FROM forecast_batches WHERE forecast_batch_id = ?",
                    (batch_id,),
                ).fetchone()

            self.assertEqual(batch_id, retry_batch_id)
            self.assertEqual(len(forecasts), 2)
            self.assertEqual(len(retry_forecasts), 2)
            self.assertEqual(len(stored_forecasts), 2)
            self.assertEqual(batch_row, ("ready",))
            self.assertEqual({forecast.symbol for forecast in forecasts}, {"BTCUSDT", "ETHUSDT"})
            self.assertEqual([forecast.to_dict() for forecast in forecasts], [forecast.to_dict() for forecast in stored_forecasts])
            self.assertTrue(all(forecast.valid_until >= forecast.target_time for forecast in forecasts))

    def test_inference_selects_models_matching_requested_timeframe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'selector.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                insert_market_events(connection, self._build_market_events_for_timeframe("BTCUSDT", "4h", 100.0))
                insert_market_events(connection, self._build_market_events_for_timeframe("ETHUSDT", "4h", 150.0))

                artifacts_1h = run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "4h", "4h")
                _, forecasts = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

            self.assertTrue(all(forecast.model_version == artifacts_1h.trend_registration.model_version for forecast in forecasts))
            self.assertTrue(all(forecast.aux_model_version == artifacts_1h.price_registration.model_version for forecast in forecasts))

    def test_inference_prefers_exact_symbol_scope_over_newer_superset_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'symbol-scope.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))

                btc_only_artifacts = run_phase_two_training(connection, ["BTCUSDT"], "1h", "4h")
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                _, forecasts = run_inference_batch(connection, ["BTCUSDT"], "1h", "4h")

            self.assertEqual(len(forecasts), 1)
            self.assertEqual(forecasts[0].symbol, "BTCUSDT")
            self.assertEqual(forecasts[0].model_version, btc_only_artifacts.trend_registration.model_version)
            self.assertEqual(forecasts[0].aux_model_version, btc_only_artifacts.price_registration.model_version)

    def test_inference_prefers_complete_model_pair_over_newer_single_family_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'paired-models.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                artifacts = run_phase_two_training(connection, ["BTCUSDT"], "1h", "4h")
                connection.execute(
                    "INSERT INTO dataset_versions(dataset_version, symbol_scope_json, horizon_scope_json, feature_names_json, source_start_time, source_end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "dataset-v2",
                        '["BTCUSDT"]',
                        '["4h"]',
                        '["return_1"]',
                        "2026-05-01T00:00:00+00:00",
                        "2026-05-02T00:00:00+00:00",
                        "2026-05-03T00:00:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO model_versions(model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "trend-only-newer",
                        "nearest-centroid-classifier",
                        "dataset-v2",
                        '["4h"]',
                        '["BTCUSDT"]',
                        '{"timeframe": "1h"}',
                        "2026-05-03T00:10:00+00:00",
                    ),
                )
                _, forecasts = run_inference_batch(connection, ["BTCUSDT"], "1h", "4h")

            self.assertEqual(len(forecasts), 1)
            self.assertEqual(forecasts[0].model_version, artifacts.trend_registration.model_version)
            self.assertEqual(forecasts[0].aux_model_version, artifacts.price_registration.model_version)

    def test_inference_recovers_pending_partial_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'pending.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                artifacts = run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

                batch_forecast_time = datetime.fromisoformat(max(row.forecast_time for row in artifacts.dataset_bundle.rows))
                batch_key = build_batch_key(
                    artifacts.trend_registration.model_version,
                    artifacts.price_registration.model_version,
                    ["BTCUSDT", "ETHUSDT"],
                    "1h",
                    "4h",
                    batch_forecast_time,
                )
                batch_id, inserted = ensure_forecast_batch(
                    connection,
                    batch_key,
                    artifacts.trend_registration.model_version,
                    "1h",
                    "4h",
                    ["BTCUSDT", "ETHUSDT"],
                    batch_forecast_time,
                )
                self.assertTrue(inserted)
                insert_forecast_records(
                    connection,
                    [
                        ForecastGenerated(
                            schema_version=SCHEMA_VERSION,
                            event_id=ForecastGenerated.new_event_id(),
                            forecast_batch_id=batch_id,
                            model_version=artifacts.trend_registration.model_version,
                            aux_model_version=artifacts.price_registration.model_version,
                            symbol="BTCUSDT",
                            timeframe="1h",
                            horizon="4h",
                            forecast_time=batch_forecast_time,
                            target_time=batch_forecast_time + timedelta(hours=4),
                            valid_until=batch_forecast_time + timedelta(hours=4),
                            trend=ForecastDirection.UP,
                            target_price=123.0,
                            confidence=0.6,
                            generated_at=datetime.now(timezone.utc),
                        )
                    ],
                )

                recovered_batch_id, recovered_forecasts = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                final_batch_status = connection.execute(
                    "SELECT batch_status FROM forecast_batches WHERE forecast_batch_id = ?",
                    (batch_id,),
                ).fetchone()

            self.assertEqual(recovered_batch_id, batch_id)
            self.assertEqual(len(recovered_forecasts), 2)
            self.assertEqual(final_batch_status, ("ready",))
            self.assertEqual({forecast.symbol for forecast in recovered_forecasts}, {"BTCUSDT", "ETHUSDT"})

    def test_inference_falls_back_when_model_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'missing-artifact.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                artifacts = run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

                (artifacts_dir / f"{artifacts.trend_registration.model_version}.json").unlink()
                batch_id, forecasts = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

            self.assertTrue(batch_id.startswith("batch:"))
            self.assertEqual(len(forecasts), 2)

    def _build_market_events_for_timeframe(self, symbol: str, timeframe: str, base_price: float) -> list[MarketEvent]:
        base_time = datetime(2099, 5, 1, 0, 0, tzinfo=timezone.utc)
        step = timedelta(hours=4)
        prices = [base_price + index * 1.25 for index in range(18)]
        events: list[MarketEvent] = []
        for index in range(1, len(prices)):
            open_time = base_time + step * (index - 1)
            open_price = prices[index - 1]
            close_price = prices[index]
            high_price = max(open_price, close_price) + 1.0
            low_price = min(open_price, close_price) - 1.0
            open_time_ms = int(open_time.timestamp() * 1000)
            events.append(
                MarketEvent(
                    schema_version=SCHEMA_VERSION,
                    event_id=f"binance:{symbol}:{timeframe}:{open_time_ms}",
                    provider="binance",
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + step,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=200 + index,
                    captured_at=open_time + step + timedelta(minutes=1),
                )
            )
        return events
