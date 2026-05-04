from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest

from services.api.handlers import ApiError, get_forecast_batch_detail, get_forecast_history, get_latest_forecasts
from services.api.server import ForecastApiHandler
from services.inference.generate import run_inference_batch
from services.pipeline.train import run_phase_two_training
import services.pipeline.backtest as backtest_module
import services.pipeline.datasets as datasets_module
import services.pipeline.registry as registry_module
from tests.testpipeline import PipelineTests
from tools.migrate import apply_all, connect


class ApiTests(PipelineTests):
    def test_handlers_return_consistent_snapshot_views(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'api.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                batch_id, _ = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")

                latest = get_latest_forecasts(connection, "1h", "4h", ["BTCUSDT"])
                history = get_forecast_history(connection, "BTCUSDT", "1h", "4h", 5)
                detail = get_forecast_batch_detail(connection, batch_id)
                route_handler = type("ConfiguredForecastApiHandler", (ForecastApiHandler,), {"database_url": database_url})
                route_payload = route_handler.__new__(route_handler)._route(
                    "/forecasts/history",
                    {"symbol": ["BTCUSDT"], "timeframe": ["1h"], "horizon": ["4h"], "limit": ["5"]},
                )

            self.assertEqual(latest["forecast_batch_id"], batch_id)
            self.assertEqual(len(latest["forecasts"]), 1)
            self.assertEqual(history["symbol"], "BTCUSDT")
            self.assertGreaterEqual(len(history["history"]), 1)
            self.assertEqual(detail["forecast_batch_id"], batch_id)
            self.assertEqual(len(detail["forecasts"]), 2)
            self.assertEqual(route_payload["symbol"], "BTCUSDT")
            self.assertGreaterEqual(len(route_payload["history"]), 1)
            self.assertEqual({forecast["symbol"] for forecast in detail["forecasts"]}, {"BTCUSDT", "ETHUSDT"})

    def test_latest_forecasts_prefers_batch_covering_watchlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'watchlist.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                full_batch_id, _ = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                eth_only_batch_id, _ = run_inference_batch(connection, ["ETHUSDT"], "1h", "4h")

                latest_btc = get_latest_forecasts(connection, "1h", "4h", ["BTCUSDT"])

            self.assertNotEqual(eth_only_batch_id, full_batch_id)
            self.assertEqual(latest_btc["forecast_batch_id"], full_batch_id)
            self.assertEqual({forecast["symbol"] for forecast in latest_btc["forecasts"]}, {"BTCUSDT"})

    def test_latest_forecasts_uses_created_at_tiebreak_for_same_forecast_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'latest-tiebreak.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                connection.execute(
                    "INSERT INTO dataset_versions(dataset_version, symbol_scope_json, horizon_scope_json, feature_names_json, source_start_time, source_end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "dataset-v1",
                        '["BTCUSDT"]',
                        '["4h"]',
                        '["return_1"]',
                        "2026-05-01T00:00:00+00:00",
                        "2026-05-02T00:00:00+00:00",
                        "2026-05-02T00:05:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO model_versions(model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "model-v1",
                        "nearest-centroid-classifier",
                        "dataset-v1",
                        '["4h"]',
                        '["BTCUSDT"]',
                        '{"timeframe": "1h"}',
                        "2026-05-02T00:10:00+00:00",
                    ),
                )
                shared_forecast_time = "2099-05-02T08:00:00+00:00"
                connection.execute(
                    "INSERT INTO forecast_batches(forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "batch:older",
                        "model-v1",
                        "1h",
                        "4h",
                        shared_forecast_time,
                        '["BTCUSDT"]',
                        "ready",
                        "2099-05-02T08:01:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO forecast_batches(forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "batch:newer",
                        "model-v1",
                        "1h",
                        "4h",
                        shared_forecast_time,
                        '["BTCUSDT"]',
                        "ready",
                        "2099-05-02T08:02:00+00:00",
                    ),
                )
                payload = {
                    "schema_version": "1.0",
                    "event_id": "forecast-event",
                    "forecast_batch_id": "batch:newer",
                    "model_version": "model-v1",
                    "aux_model_version": None,
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "horizon": "4h",
                    "forecast_time": shared_forecast_time,
                    "target_time": "2099-05-02T12:00:00+00:00",
                    "valid_until": "2099-05-02T14:00:00+00:00",
                    "trend": "up",
                    "target_price": 123.0,
                    "confidence": 0.7,
                    "generated_at": "2099-05-02T08:02:00+00:00",
                }
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast:batch:newer:BTCUSDT:1h:4h",
                        "batch:newer",
                        "model-v1",
                        "BTCUSDT",
                        "1h",
                        "4h",
                        shared_forecast_time,
                        "2099-05-02T12:00:00+00:00",
                        "up",
                        123.0,
                        0.7,
                        "2099-05-02T08:02:00+00:00",
                        json.dumps(payload),
                    ),
                )
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast:batch:older:BTCUSDT:1h:4h",
                        "batch:older",
                        "model-v1",
                        "BTCUSDT",
                        "1h",
                        "4h",
                        shared_forecast_time,
                        "2099-05-02T12:00:00+00:00",
                        "down",
                        120.0,
                        0.6,
                        "2099-05-02T08:01:00+00:00",
                        json.dumps({**payload, "forecast_batch_id": "batch:older", "trend": "down", "target_price": 120.0, "confidence": 0.6, "generated_at": "2099-05-02T08:01:00+00:00"}),
                    ),
                )
                latest = get_latest_forecasts(connection, "1h", "4h", ["BTCUSDT"])

            self.assertEqual(latest["forecast_batch_id"], "batch:newer")
            self.assertEqual(latest["forecasts"][0]["trend"], "up")

    def test_latest_forecasts_respects_valid_until_beyond_target_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'valid-until.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                connection.execute(
                    "INSERT INTO dataset_versions(dataset_version, symbol_scope_json, horizon_scope_json, feature_names_json, source_start_time, source_end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "dataset-v1",
                        '["BTCUSDT", "ETHUSDT"]',
                        '["4h"]',
                        '["return_1"]',
                        "2026-05-01T00:00:00+00:00",
                        "2026-05-02T00:00:00+00:00",
                        "2026-05-02T00:05:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO model_versions(model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "model-v1",
                        "nearest-centroid-classifier",
                        "dataset-v1",
                        '["4h"]',
                        '["BTCUSDT", "ETHUSDT"]',
                        '{"timeframe": "1h"}',
                        "2026-05-02T00:10:00+00:00",
                    ),
                )
                forecast_time = "2026-05-02T08:00:00+00:00"
                connection.execute(
                    "INSERT INTO forecast_batches(forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "batch:valid-until",
                        "model-v1",
                        "1h",
                        "4h",
                        forecast_time,
                        '["BTCUSDT", "ETHUSDT"]',
                        "ready",
                        "2026-05-02T08:01:00+00:00",
                    ),
                )
                btc_payload = {
                    "schema_version": "1.0",
                    "event_id": "forecast-valid-until-btc",
                    "forecast_batch_id": "batch:valid-until",
                    "model_version": "model-v1",
                    "aux_model_version": None,
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "horizon": "4h",
                    "forecast_time": forecast_time,
                    "target_time": "2026-05-02T12:00:00+00:00",
                    "valid_until": "2026-05-02T12:00:00+00:00",
                    "trend": "up",
                    "target_price": 123.0,
                    "confidence": 0.7,
                    "generated_at": "2026-05-02T08:02:00+00:00",
                }
                eth_payload = {
                    **btc_payload,
                    "event_id": "forecast-valid-until-eth",
                    "symbol": "ETHUSDT",
                    "valid_until": "2099-05-02T14:00:00+00:00",
                }
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast:batch:valid-until:BTCUSDT:1h:4h",
                        "batch:valid-until",
                        "model-v1",
                        "BTCUSDT",
                        "1h",
                        "4h",
                        forecast_time,
                        "2026-05-02T12:00:00+00:00",
                        "up",
                        123.0,
                        0.7,
                        "2026-05-02T08:02:00+00:00",
                        json.dumps(btc_payload),
                    ),
                )
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast:batch:valid-until:ETHUSDT:1h:4h",
                        "batch:valid-until",
                        "model-v1",
                        "ETHUSDT",
                        "1h",
                        "4h",
                        forecast_time,
                        "2026-05-02T12:00:00+00:00",
                        "up",
                        123.0,
                        0.7,
                        "2026-05-02T08:02:00+00:00",
                        json.dumps(eth_payload),
                    ),
                )
                with self.assertRaises(ApiError):
                    get_latest_forecasts(connection, "1h", "4h", ["BTCUSDT"])
                latest_eth = get_latest_forecasts(connection, "1h", "4h", ["ETHUSDT"])

            self.assertEqual(latest_eth["forecast_batch_id"], "batch:valid-until")
            self.assertEqual(latest_eth["forecasts"][0]["valid_until"], "2099-05-02T14:00:00+00:00")

    def test_history_excludes_pending_batch_forecasts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'pending-history.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                connection.execute(
                    "INSERT INTO dataset_versions(dataset_version, symbol_scope_json, horizon_scope_json, feature_names_json, source_start_time, source_end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "dataset-v1",
                        '["BTCUSDT"]',
                        '["4h"]',
                        '["return_1"]',
                        "2026-05-01T00:00:00+00:00",
                        "2026-05-02T00:00:00+00:00",
                        "2026-05-02T00:05:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO model_versions(model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "model-v1",
                        "nearest-centroid-classifier",
                        "dataset-v1",
                        '["4h"]',
                        '["BTCUSDT"]',
                        '{"timeframe": "1h"}',
                        "2026-05-02T00:10:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO forecast_batches(forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "batch:pending",
                        "model-v1",
                        "1h",
                        "4h",
                        "2099-05-02T08:00:00+00:00",
                        '["BTCUSDT"]',
                        "pending",
                        "2099-05-02T08:01:00+00:00",
                    ),
                )
                payload = {
                    "schema_version": "1.0",
                    "event_id": "forecast-pending",
                    "forecast_batch_id": "batch:pending",
                    "model_version": "model-v1",
                    "aux_model_version": None,
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "horizon": "4h",
                    "forecast_time": "2099-05-02T08:00:00+00:00",
                    "target_time": "2099-05-02T12:00:00+00:00",
                    "valid_until": "2099-05-02T14:00:00+00:00",
                    "trend": "up",
                    "target_price": 123.0,
                    "confidence": 0.7,
                    "generated_at": "2099-05-02T08:02:00+00:00",
                }
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast:pending:BTCUSDT:1h:4h",
                        "batch:pending",
                        "model-v1",
                        "BTCUSDT",
                        "1h",
                        "4h",
                        "2099-05-02T08:00:00+00:00",
                        "2099-05-02T12:00:00+00:00",
                        "up",
                        123.0,
                        0.7,
                        "2099-05-02T08:02:00+00:00",
                        json.dumps(payload),
                    ),
                )
                history = get_forecast_history(connection, "BTCUSDT", "1h", "4h", 5)

            self.assertEqual(history["history"], [])

    def test_history_limit_above_cap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'limit-cap.db'}"
            apply_all(database_url, "up")
            with connect(database_url) as connection:
                with self.assertRaises(ValueError):
                    get_forecast_history(connection, "BTCUSDT", "1h", "4h", 201)

    def test_server_returns_generic_500_for_unexpected_error(self) -> None:
        handler_class = type("ConfiguredForecastApiHandler", (ForecastApiHandler,), {"database_url": "sqlite:///./missing.db"})
        handler = handler_class.__new__(handler_class)
        handler.path = "/forecasts/latest?timeframe=1h&horizon=4h"
        captured: list[tuple[int, dict]] = []
        handler._route = lambda path, query: (_ for _ in ()).throw(RuntimeError("no such table: forecast_batches"))
        handler._write_json = lambda status, payload: captured.append((status, payload))

        handler.do_GET()

        self.assertEqual(captured, [(500, {"error": "internal server error"})])
