from __future__ import annotations

from datetime import datetime, timezone
import sqlite3



def notification_slot(scheduled_for: datetime) -> datetime:
    return scheduled_for.replace(second=0, microsecond=0)



def notification_run_id(delivery_key: str, scheduled_for: datetime) -> str:
    return f"notification:{delivery_key}:{notification_slot(scheduled_for).isoformat()}"



def create_notification_run(
    connection: sqlite3.Connection,
    delivery_key: str,
    forecast_batch_id: str,
    scheduled_for: datetime,
    message_preview: str,
    status: str,
) -> tuple[str, bool]:
    run_id = notification_run_id(delivery_key, scheduled_for)
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO notification_runs(
            notification_run_id,
            forecast_batch_id,
            delivery_channel,
            scheduled_for,
            message_preview,
            sent_at,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            forecast_batch_id,
            "telegram",
            notification_slot(scheduled_for).isoformat(),
            message_preview,
            None,
            status,
        ),
    )
    return run_id, cursor.rowcount == 1



def load_notification_run(connection: sqlite3.Connection, notification_run_id: str) -> dict | None:
    row = connection.execute(
        "SELECT notification_run_id, forecast_batch_id, scheduled_for, message_preview, sent_at, status FROM notification_runs WHERE notification_run_id = ?",
        (notification_run_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "notification_run_id": row[0],
        "forecast_batch_id": row[1],
        "scheduled_for": row[2],
        "message_preview": row[3],
        "sent_at": row[4],
        "status": row[5],
    }



def load_notification_run_for_slot(connection: sqlite3.Connection, delivery_key: str, scheduled_for: datetime) -> dict | None:
    return load_notification_run(connection, notification_run_id(delivery_key, scheduled_for))



def claim_notification_send(connection: sqlite3.Connection, notification_run_id: str, current_status: str, retry_count: int) -> bool:
    next_status = f"sending:{retry_count}"
    cursor = connection.execute(
        "UPDATE notification_runs SET status = ? WHERE notification_run_id = ? AND status = ?",
        (next_status, notification_run_id, current_status),
    )
    return cursor.rowcount == 1



def mark_notification_sent(connection: sqlite3.Connection, notification_run_id: str) -> None:
    connection.execute(
        "UPDATE notification_runs SET sent_at = ?, status = ? WHERE notification_run_id = ?",
        (datetime.now(timezone.utc).isoformat(), "sent", notification_run_id),
    )



def mark_notification_failed(connection: sqlite3.Connection, notification_run_id: str, retry_count: int) -> None:
    connection.execute(
        "UPDATE notification_runs SET status = ? WHERE notification_run_id = ?",
        (f"failed:{retry_count}", notification_run_id),
    )



def mark_notification_unknown(connection: sqlite3.Connection, notification_run_id: str, retry_count: int) -> None:
    connection.execute(
        "UPDATE notification_runs SET status = ? WHERE notification_run_id = ?",
        (f"unknown:{retry_count}", notification_run_id),
    )



def notification_retry_count(status: str) -> int:
    if status.startswith("failed:") or status.startswith("unknown:"):
        return int(status.split(":", 1)[1])
    return 0
