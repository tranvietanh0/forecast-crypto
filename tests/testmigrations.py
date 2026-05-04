from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.migrate import apply_all, connect


class MigrationTests(unittest.TestCase):
    def test_up_and_down_migrations_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'phase1.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                expected_tables = {
                    "schema_migrations",
                    "raw_market_events",
                    "dataset_versions",
                    "model_versions",
                    "forecast_batches",
                    "forecasts",
                    "notification_runs",
                    "realized_outcomes",
                    "event_log",
                }
                self.assertTrue(expected_tables.issubset(tables))

                connection.execute(
                    "INSERT INTO dataset_versions(dataset_version, symbol_scope_json, horizon_scope_json, feature_names_json, source_start_time, source_end_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "dataset-v1",
                        '["BTCUSDT"]',
                        '["4h"]',
                        '["rsi_14", "volatility_24h"]',
                        "2026-05-01T00:00:00+00:00",
                        "2026-05-02T00:00:00+00:00",
                        "2026-05-02T00:05:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO model_versions(model_version, model_family, dataset_version, horizons_json, symbol_scope_json, metrics_json, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "model-v1",
                        "xgboost",
                        "dataset-v1",
                        '["4h"]',
                        '["BTCUSDT"]',
                        '{"direction_accuracy": 0.61}',
                        "2026-05-02T00:10:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO forecast_batches(forecast_batch_id, model_version, timeframe, horizon, forecast_time, coin_universe_json, batch_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "batch-1",
                        "model-v1",
                        "1h",
                        "4h",
                        "2026-05-02T01:00:00+00:00",
                        '["BTCUSDT"]',
                        "generated",
                        "2026-05-02T01:01:00+00:00",
                    ),
                )
                connection.execute(
                    "INSERT INTO forecasts(forecast_id, forecast_batch_id, model_version, symbol, timeframe, horizon, forecast_time, target_time, trend, target_price, confidence, generated_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "forecast-1",
                        "batch-1",
                        "model-v1",
                        "BTCUSDT",
                        "1h",
                        "4h",
                        "2026-05-02T01:00:00+00:00",
                        "2026-05-02T05:00:00+00:00",
                        "up",
                        97250.0,
                        0.78,
                        "2026-05-02T01:01:00+00:00",
                        '{"trend": "up", "target_price": 97250.0}',
                    ),
                )
                forecast_row = connection.execute(
                    "SELECT symbol, trend, target_price FROM forecasts WHERE forecast_id = ?",
                    ("forecast-1",),
                ).fetchone()
                self.assertEqual(forecast_row, ("BTCUSDT", "up", 97250.0))

            apply_all(database_url, "down")

            raw_connection = sqlite3.connect(str(Path(temp_dir) / "phase1.db"))
            try:
                remaining_tables = {
                    row[0]
                    for row in raw_connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                self.assertEqual(remaining_tables, {"schema_migrations"})
            finally:
                raw_connection.close()

    def test_repeat_up_only_applies_pending_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'phase1-repeat.db'}"
            apply_all(database_url, "up")
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                rows = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                self.assertEqual(rows, [("0001_phase1_foundation",)])
