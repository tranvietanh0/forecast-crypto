from __future__ import annotations


def format_telegram_summary(latest_payload: dict) -> str:
    forecasts = latest_payload["forecasts"]
    header = (
        f"Forecast batch {latest_payload['forecast_batch_id']}\n"
        f"Timeframe: {latest_payload['timeframe']} | Horizon: {latest_payload['horizon']}"
    )
    lines = [header]
    for forecast in forecasts:
        presentation = forecast["presentation"]
        lines.append(
            " • "
            f"{forecast['symbol']}: {presentation['trend_label']} | "
            f"{presentation['target_price_text']} | "
            f"conf {presentation['confidence_text']}"
        )
    return "\n".join(lines)
