import json
from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from app.workers.tasks.dlq_tasks import get_dlq_stats, handle_failed_task, replay_failed_task


class TestDLQHandling:

    def test_handle_failed_task_creates_dlq_record(self):
        failed_task_data = {
            "task_id": str(uuid4()),
            "task_name": "process_deposit",
            "args": ["transaction_id", "account_id", "100.00", "user_id"],
            "kwargs": {},
            "exception_type": "ValueError",
            "exception_message": "Invalid transaction data",
            "traceback": "Traceback...",
            "failed_at": datetime.now(UTC).isoformat(),
            "retry_count": 3,
        }

        with patch("app.workers.tasks.dlq_tasks.SessionLocal") as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db
            mock_db.query().filter().first.return_value = None

            result = handle_failed_task(failed_task_data)

            assert result["status"] == "stored"
            assert "dlq_record_id" in result
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    def test_handle_failed_task_prevents_duplicates(self):
        task_id = str(uuid4())
        failed_task_data = {
            "task_id": task_id,
            "task_name": "process_deposit",
            "args": [],
            "kwargs": {},
            "exception_type": "ValueError",
            "exception_message": "Test error",
            "traceback": "Traceback...",
            "failed_at": datetime.now(UTC).isoformat(),
            "retry_count": 3,
        }

        with patch("app.workers.tasks.dlq_tasks.SessionLocal") as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            existing_record = Mock()
            existing_record.task_id = task_id
            mock_db.query().filter().first.return_value = existing_record

            result = handle_failed_task(failed_task_data)

            assert result["status"] == "duplicate"
            assert result["task_id"] == task_id
            mock_db.add.assert_not_called()

    def test_replay_failed_task_requeues_to_main_queue(self):
        dlq_record_id = str(uuid4())

        with patch("app.workers.tasks.dlq_tasks.SessionLocal") as mock_session_local:
            with patch("app.workers.tasks.dlq_tasks.celery_app") as mock_celery:
                mock_db = Mock()
                mock_session_local.return_value = mock_db

                failed_task = Mock()
                failed_task.id = dlq_record_id
                failed_task.task_name = "process_deposit"
                failed_task.args = json.dumps(["arg1", "arg2"])
                failed_task.kwargs = json.dumps({"key": "value"})
                failed_task.replayed_at = None
                mock_db.query().filter().first.return_value = failed_task

                mock_result = Mock()
                mock_result.id = str(uuid4())
                mock_celery.send_task.return_value = mock_result

                result = replay_failed_task(dlq_record_id)

                assert result["status"] == "replayed"
                assert "new_task_id" in result
                mock_celery.send_task.assert_called_once()

                call_kwargs = mock_celery.send_task.call_args.kwargs
                assert call_kwargs["queue"] == "transactions"

    def test_replay_failed_task_prevents_duplicate_replay(self):
        dlq_record_id = str(uuid4())

        with patch("app.workers.tasks.dlq_tasks.SessionLocal") as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            failed_task = Mock()
            failed_task.replayed_at = datetime.now(UTC)
            failed_task.replay_status = "QUEUED"
            mock_db.query().filter().first.return_value = failed_task

            result = replay_failed_task(dlq_record_id)

            assert result["status"] == "already_replayed"

    def test_get_dlq_stats_returns_metrics(self):
        with patch("app.workers.tasks.dlq_tasks.SessionLocal") as mock_session_local:
            mock_db = Mock()
            mock_session_local.return_value = mock_db

            mock_db.query().scalar.return_value = 10
            mock_db.query().group_by().all.return_value = [
                ("process_deposit", 5),
                ("process_withdrawal", 3),
                ("send_webhook_notification", 2),
            ]

            result = get_dlq_stats()

            assert "total_failed_tasks" in result
            assert "tasks_by_type" in result
            assert "recent_failures_24h" in result
            assert "unreplayed_tasks" in result


class TestDLQConfiguration:

    def test_dlq_task_has_get_db_method(self):
        from app.workers.base_task import DLQTask

        task = DLQTask()

        assert hasattr(task, "get_db")
        assert callable(task.get_db)

    def test_dlq_queues_configured_in_celery(self):
        from app.workers.celery_app import celery_app

        queue_names = [q.name for q in celery_app.conf.task_queues]

        assert "transactions.dlq" in queue_names
        assert "webhooks.dlq" in queue_names

        assert "transactions" in queue_names
        assert "webhooks" in queue_names
