from __future__ import annotations

from datetime import datetime, timezone

from contracts.events import ForecastDirection, ForecastGenerated


def build_forecast_view(forecast: ForecastGenerated) -> dict:
    return {
        **forecast.to_dict(),
        "presentation": {
            "trend_label": trend_label(forecast.trend),
            "trend_badge": trend_badge(forecast.trend),
            "target_price_text": format_price(forecast.target_price),
            "confidence_text": format_confidence(forecast.confidence),
            "status": forecast_status(forecast),
        },
    }


def trend_label(trend: ForecastDirection) -> str:
    if trend == ForecastDirection.UP:
        return "Bullish"
    if trend == ForecastDirection.DOWN:
        return "Bearish"
    return "Neutral"


def trend_badge(trend: ForecastDirection) -> str:
    if trend == ForecastDirection.UP:
        return "up"
    if trend == ForecastDirection.DOWN:
        return "down"
    return "neutral"


def format_price(value: float) -> str:
    return f"${value:,.2f}"


def format_confidence(value: float) -> str:
    return f"{value * 100:.1f}%"


def forecast_status(forecast: ForecastGenerated) -> str:
    now = datetime.now(timezone.utc)
    return "expired" if forecast.valid_until < now else "active"
