from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from contracts.config import RuntimeSecrets
from services.telegram.formatter import format_telegram_summary
from services.telegram.scheduler import ScheduleError, should_run
import services.telegram.service as telegram_service_module
from services.telegram.service import build_preview, send_latest_summary
from tests.testpipeline import PipelineTests
import services.pipeline.backtest as backtest_module
import services.pipeline.datasets as datasets_module
import services.pipeline.registry as registry_module
from services.pipeline.train import run_phase_two_training
from services.inference.generate import run_inference_batch
from tools.migrate import apply_all, connect


class TelegramTests(PipelineTests):
    def test_formatter_and_preview_share_latest_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'telegram-preview.db'}"
            apply_all(database_url, "up")

            with connect(database_url) as connection:
                from services.ingestion.storage import insert_market_events
                insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                insert_market_events(connection, self._build_market_events("ETHUSDT", 150.0, trending=False))
                run_phase_two_training(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                batch_id, _ = run_inference_batch(connection, ["BTCUSDT", "ETHUSDT"], "1h", "4h")
                payload, preview = build_preview(connection, "1h", "4h", ["BTCUSDT", "ETHUSDT"])

            self.assertEqual(payload["forecast_batch_id"], batch_id)
            self.assertIn(batch_id, preview)
            self.assertIn("BTCUSDT", preview)
            self.assertIn("ETHUSDT", preview)

    def test_send_latest_summary_supports_dry_run_and_live_send(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'telegram-send.db'}"
            apply_all(database_url, "up")

            runtime = RuntimeSecrets(
                database_url=database_url,
                telegram_bot_token="bot-token",
                telegram_chat_id="chat-id",
                market_data_api_key=None,
            )
            sent_messages = []
            original_sender = telegram_service_module.send_telegram_message
            telegram_service_module.send_telegram_message = lambda token, chat_id, text: sent_messages.append((token, chat_id, text)) or {"ok": True}
            try:
                with connect(database_url) as connection:
                    from services.ingestion.storage import insert_market_events
                    insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                    run_phase_two_training(connection, ["BTCUSDT"], "1h", "4h")
                    run_inference_batch(connection, ["BTCUSDT"], "1h", "4h")

                    scheduled_for = datetime(2099, 5, 1, 9, 30, 12, tzinfo=timezone.utc)
                    dry_run_result = send_latest_summary(
                        connection,
                        runtime,
                        "1h",
                        "4h",
                        ["BTCUSDT"],
                        scheduled_for,
                        dry_run=True,
                    )
                    live_scheduled_for = scheduled_for.replace(minute=31)
                    live_result = send_latest_summary(
                        connection,
                        runtime,
                        "1h",
                        "4h",
                        ["BTCUSDT"],
                        live_scheduled_for,
                        dry_run=False,
                    )
                    duplicate_live_result = send_latest_summary(
                        connection,
                        runtime,
                        "1h",
                        "4h",
                        ["BTCUSDT"],
                        live_scheduled_for.replace(second=45),
                        dry_run=False,
                    )
                    statuses = connection.execute(
                        "SELECT status FROM notification_runs ORDER BY scheduled_for ASC"
                    ).fetchall()
            finally:
                telegram_service_module.send_telegram_message = original_sender

            self.assertTrue(dry_run_result["dry_run"])
            self.assertFalse(live_result["dry_run"])
            self.assertFalse(duplicate_live_result["dry_run"])
            self.assertEqual(len(sent_messages), 1)
            self.assertEqual(sent_messages[0][0], "bot-token")
            self.assertIn("BTCUSDT", sent_messages[0][2])
            self.assertEqual(statuses[0], ("dry-run",))
            self.assertEqual(statuses[1], ("sent",))

    def test_send_latest_summary_dedupes_duplicate_watchlist_and_respects_sending_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_dir = Path(temp_dir) / "artifacts"
            datasets_module.ARTIFACTS_DIR = artifacts_dir
            registry_module.ARTIFACTS_DIR = artifacts_dir
            backtest_module.ARTIFACTS_DIR = artifacts_dir

            database_url = f"sqlite:///{Path(temp_dir) / 'telegram-lock.db'}"
            apply_all(database_url, "up")

            runtime = RuntimeSecrets(
                database_url=database_url,
                telegram_bot_token="bot-token",
                telegram_chat_id="chat-id",
                market_data_api_key=None,
            )
            sent_messages = []
            original_sender = telegram_service_module.send_telegram_message
            telegram_service_module.send_telegram_message = lambda token, chat_id, text: sent_messages.append((token, chat_id, text)) or {"ok": True}
            try:
                with connect(database_url) as connection:
                    from services.ingestion.storage import insert_market_events
                    insert_market_events(connection, self._build_market_events("BTCUSDT", 100.0, trending=False))
                    run_phase_two_training(connection, ["BTCUSDT"], "1h", "4h")
                    run_inference_batch(connection, ["BTCUSDT"], "1h", "4h")

                    scheduled_for = datetime(2099, 5, 1, 9, 45, 10, tzinfo=timezone.utc)
                    first_result = send_latest_summary(
                        connection,
                        runtime,
                        "1h",
                        "4h",
                        ["BTCUSDT", "BTCUSDT"],
                        scheduled_for,
                        dry_run=False,
                    )
                    connection.execute(
                        "UPDATE notification_runs SET status = ? WHERE notification_run_id = ?",
                        ("sending:1", first_result["notification_run_id"]),
                    )
                    second_result = send_latest_summary(
                        connection,
                        runtime,
                        "1h",
                        "4h",
                        ["BTCUSDT"],
                        scheduled_for.replace(second=50),
                        dry_run=False,
                    )
            finally:
                telegram_service_module.send_telegram_message = original_sender

            self.assertEqual(len(sent_messages), 1)
            self.assertEqual(second_result["status"], "sending:1")

    def test_scheduler_matches_configured_cadence(self) -> None:
        self.assertTrue(should_run("15 */4 * * *", datetime(2099, 5, 1, 8, 15, tzinfo=timezone.utc)))
        self.assertFalse(should_run("15 */4 * * *", datetime(2099, 5, 1, 8, 10, tzinfo=timezone.utc)))

    def test_scheduler_matches_cron_day_of_week_convention(self) -> None:
        self.assertTrue(should_run("15 9 * * 1", datetime(2099, 5, 4, 9, 15, tzinfo=timezone.utc)))
        self.assertFalse(should_run("15 9 * * 1", datetime(2099, 5, 5, 9, 15, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 10 * * 0", datetime(2099, 5, 10, 10, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 10 * * 1-5", datetime(2099, 5, 4, 10, 0, tzinfo=timezone.utc)))
        self.assertFalse(should_run("0 10 * * 1-5", datetime(2099, 5, 10, 10, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 8,20 * * *", datetime(2099, 5, 10, 20, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 9 1 * 1", datetime(2099, 6, 1, 9, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 9 1 * 1", datetime(2099, 6, 8, 9, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 9 */2 * *", datetime(2099, 5, 3, 9, 0, tzinfo=timezone.utc)))
        self.assertFalse(should_run("0 9 */2 * *", datetime(2099, 5, 2, 9, 0, tzinfo=timezone.utc)))
        self.assertTrue(should_run("0 9 * */4 *", datetime(2099, 5, 1, 9, 0, tzinfo=timezone.utc)))
        self.assertFalse(should_run("0 9 * */4 *", datetime(2099, 4, 1, 9, 0, tzinfo=timezone.utc)))

    def test_scheduler_rejects_invalid_cron_values(self) -> None:
        with self.assertRaises(ScheduleError):
            should_run("61 9 * * *", datetime(2099, 5, 1, 9, 0, tzinfo=timezone.utc))
        with self.assertRaises(ScheduleError):
            should_run("0 9 */0 * *", datetime(2099, 5, 1, 9, 0, tzinfo=timezone.utc))
