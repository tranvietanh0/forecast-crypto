from __future__ import annotations

from pathlib import Path
import unittest

from contracts.config import ConfigValidationError, load_config, validate_runtime_env


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = Path(__file__).resolve().parent.parent / "config" / "defaults.json"

    def test_load_config_reads_defaults_and_env_overrides(self) -> None:
        config = load_config(
            self.config_path,
            env={
                "DATABASE_URL": "sqlite:///:memory:",
                "COIN_UNIVERSE": "BTCUSDT,ETHUSDT,XRPUSDT",
                "FORECAST_HORIZONS": "1h,4h",
                "RETENTION_DAYS": "30",
                "FORECAST_CRON": "5 * * * *",
                "TELEGRAM_CRON": "10 * * * *",
            },
        )

        self.assertEqual(config.coin_universe, ["BTCUSDT", "ETHUSDT", "XRPUSDT"])
        self.assertEqual(config.forecast_horizons, ["1h", "4h"])
        self.assertEqual(config.retention_days, 30)
        self.assertEqual(config.scheduler.forecast_cron, "5 * * * *")
        self.assertEqual(config.runtime.database_url, "sqlite:///:memory:")

    def test_validate_runtime_env_fails_fast_when_required_env_missing(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_runtime_env({})

    def test_load_config_does_not_fallback_to_process_env_when_empty_mapping_is_passed(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_config(self.config_path, env={})
