from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from contracts.config import RuntimeSecrets
from services.api.handlers import get_latest_forecasts
from services.telegram.client import TelegramError, send_telegram_message
from services.telegram.formatter import format_telegram_summary
from services.telegram.scheduler import should_run
from services.telegram.storage import (
    claim_notification_send,
    create_notification_run,
    load_notification_run,
    load_notification_run_for_slot,
    mark_notification_failed,
    mark_notification_sent,
    mark_notification_unknown,
    notification_retry_count,
)


class TelegramServiceError(RuntimeError):
    pass



def delivery_key(timeframe: str, horizon: str, watchlist: list[str]) -> str:
    canonical_watchlist = ",".join(sorted(set(watchlist))) if watchlist else "all"
    return f"telegram:{timeframe}:{horizon}:{canonical_watchlist}"



def build_preview(
    connection: sqlite3.Connection,
    timeframe: str,
    horizon: str,
    watchlist: list[str],
) -> tuple[dict, str]:
    latest_payload = get_latest_forecasts(connection, timeframe, horizon, watchlist)
    return latest_payload, format_telegram_summary(latest_payload)



def send_latest_summary(
    connection: sqlite3.Connection,
    runtime: RuntimeSecrets,
    timeframe: str,
    horizon: str,
    watchlist: list[str],
    scheduled_for: datetime,
    dry_run: bool = False,
) -> dict:
    key = delivery_key(timeframe, horizon, watchlist)
    existing_run = load_notification_run_for_slot(connection, key, scheduled_for)
    if existing_run is not None:
        if dry_run:
            return {
                "notification_run_id": existing_run["notification_run_id"],
                "forecast_batch_id": existing_run["forecast_batch_id"],
                "message_preview": existing_run["message_preview"],
                "dry_run": True,
            }
        if existing_run["status"] in {"sent", "pending"} or existing_run["status"].startswith("sending:") or existing_run["status"].startswith("unknown:"):
            return {
                "notification_run_id": existing_run["notification_run_id"],
                "forecast_batch_id": existing_run["forecast_batch_id"],
                "message_preview": existing_run["message_preview"],
                "dry_run": False,
                "status": existing_run["status"],
            }

    latest_payload, preview = build_preview(connection, timeframe, horizon, watchlist)
    if not dry_run and (not runtime.telegram_bot_token or not runtime.telegram_chat_id):
        raise TelegramServiceError("Telegram bot token and chat ID are required for live delivery")

    with connection:
        notification_run_id, created = create_notification_run(
            connection,
            key,
            latest_payload["forecast_batch_id"],
            scheduled_for,
            preview,
            "dry-run" if dry_run else "pending",
        )
        notification_run = load_notification_run(connection, notification_run_id)

    if notification_run is None:
        raise TelegramServiceError("Failed to create notification audit row")

    if dry_run:
        return {
            "notification_run_id": notification_run_id,
            "forecast_batch_id": latest_payload["forecast_batch_id"],
            "message_preview": preview,
            "dry_run": True,
        }

    if notification_run["status"] == "sent":
        return {
            "notification_run_id": notification_run_id,
            "forecast_batch_id": latest_payload["forecast_batch_id"],
            "message_preview": preview,
            "dry_run": False,
        }
    if not created and notification_run["status"] == "pending" and notification_run["sent_at"] is None:
        return {
            "notification_run_id": notification_run_id,
            "forecast_batch_id": latest_payload["forecast_batch_id"],
            "message_preview": preview,
            "dry_run": False,
            "status": "pending",
        }
    if notification_run["status"].startswith("sending:") or notification_run["status"].startswith("unknown:"):
        return {
            "notification_run_id": notification_run_id,
            "forecast_batch_id": latest_payload["forecast_batch_id"],
            "message_preview": preview,
            "dry_run": False,
            "status": notification_run["status"],
        }

    current_status = notification_run["status"]
    retry_count = notification_retry_count(current_status) + 1
    with connection:
        claimed = claim_notification_send(connection, notification_run_id, current_status, retry_count)
    if not claimed:
        refreshed = load_notification_run(connection, notification_run_id)
        return {
            "notification_run_id": notification_run_id,
            "forecast_batch_id": latest_payload["forecast_batch_id"],
            "message_preview": preview,
            "dry_run": False,
            "status": refreshed["status"] if refreshed else "unknown",
        }

    try:
        send_telegram_message(runtime.telegram_bot_token, runtime.telegram_chat_id, preview)
        with connection:
            mark_notification_sent(connection, notification_run_id)
    except TelegramError:
        with connection:
            mark_notification_failed(connection, notification_run_id, retry_count)
        raise
    except Exception:
        with connection:
            mark_notification_unknown(connection, notification_run_id, retry_count)
        raise
    return {
        "notification_run_id": notification_run_id,
        "forecast_batch_id": latest_payload["forecast_batch_id"],
        "message_preview": preview,
        "dry_run": False,
        "status": "sent",
    }



def should_send_telegram(cron_expression: str, now: datetime | None = None) -> bool:
    current_time = now or datetime.now(timezone.utc)
    return should_run(cron_expression, current_time)
