from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import json
import os


class ConfigValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    candles_path: str


@dataclass(frozen=True)
class SchedulerConfig:
    forecast_cron: str
    telegram_cron: str


@dataclass(frozen=True)
class RuntimeSecrets:
    database_url: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    market_data_api_key: str | None


@dataclass(frozen=True)
class AppConfig:
    coin_universe: list[str]
    forecast_horizons: list[str]
    providers: dict[str, ProviderConfig]
    scheduler: SchedulerConfig
    retention_days: int
    runtime: RuntimeSecrets


REQUIRED_ENV_VARS = ("DATABASE_URL",)


def validate_runtime_env(env: Mapping[str, str] | None = None) -> RuntimeSecrets:
    source = os.environ if env is None else env
    missing = [key for key in REQUIRED_ENV_VARS if not source.get(key)]
    if missing:
        joined = ", ".join(missing)
        raise ConfigValidationError(f"Missing required environment variables: {joined}")

    return RuntimeSecrets(
        database_url=source["DATABASE_URL"],
        telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=source.get("TELEGRAM_CHAT_ID") or None,
        market_data_api_key=source.get("MARKET_DATA_API_KEY") or None,
    )


def _normalize_symbol_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        symbols = value
    else:
        symbols = [item.strip() for item in value.split(",") if item.strip()]

    if not symbols:
        raise ConfigValidationError("coin_universe must not be empty")
    return symbols


def _normalize_horizon_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        horizons = value
    else:
        horizons = [item.strip() for item in value.split(",") if item.strip()]

    if not horizons:
        raise ConfigValidationError("forecast_horizons must not be empty")
    return horizons


def load_config(config_path: str | Path, env: Mapping[str, str] | None = None) -> AppConfig:
    source = os.environ if env is None else env
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))

    coin_universe = _normalize_symbol_list(source.get("COIN_UNIVERSE", raw["coin_universe"]))
    forecast_horizons = _normalize_horizon_list(source.get("FORECAST_HORIZONS", raw["forecast_horizons"]))
    providers = {
        key: ProviderConfig(
            name=value["name"],
            base_url=value["base_url"],
            candles_path=value["candles_path"],
        )
        for key, value in raw["providers"].items()
    }
    scheduler = SchedulerConfig(
        forecast_cron=source.get("FORECAST_CRON", raw["scheduler"]["forecast_cron"]),
        telegram_cron=source.get("TELEGRAM_CRON", raw["scheduler"]["telegram_cron"]),
    )
    retention_days = int(source.get("RETENTION_DAYS", raw["retention_days"]))
    if retention_days <= 0:
        raise ConfigValidationError("retention_days must be greater than zero")

    return AppConfig(
        coin_universe=coin_universe,
        forecast_horizons=forecast_horizons,
        providers=providers,
        scheduler=scheduler,
        retention_days=retention_days,
        runtime=validate_runtime_env(source),
    )
