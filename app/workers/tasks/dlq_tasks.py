import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func

from app.core.logging import get_logger
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.models.failed_task import FailedTask
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.dlq_tasks.handle_failed_task")
def handle_failed_task(failed_task_data: dict[str, Any]) -> dict[str, str]:
    logger.error(
        "dlq_task_received",
        task_id=failed_task_data.get("task_id"),
        task_name=failed_task_data.get("task_name"),
        exception=failed_task_data.get("exception_message"),
    )

    db = SessionLocal()

    try:
        # check if already in DLQ. duplicae?
        existing = (
            db.query(FailedTask).filter(FailedTask.task_id == failed_task_data["task_id"]).first()
        )

        if existing:
            logger.warning(
                "dlq_duplicate_task_ignored",
                task_id=failed_task_data["task_id"],
            )
            return {"status": "duplicate", "task_id": failed_task_data["task_id"]}

        # Create DLQ record
        failed_task = FailedTask(
            task_id=failed_task_data["task_id"],
            task_name=failed_task_data["task_name"],
            args=json.dumps(failed_task_data.get("args", [])),
            kwargs=json.dumps(failed_task_data.get("kwargs", {})),
            exception_type=failed_task_data["exception_type"],
            exception_message=failed_task_data["exception_message"],
            traceback=failed_task_data.get("traceback", ""),
            retry_count=str(failed_task_data.get("retry_count", 0)),
            failed_at=datetime.fromisoformat(failed_task_data["failed_at"]),
        )

        db.add(failed_task)
        db.commit()

        logger.info(
            "dlq_task_stored",
            task_id=failed_task_data["task_id"],
            task_name=failed_task_data["task_name"],
            dlq_record_id=str(failed_task.id),
        )

        return {
            "status": "stored",
            "task_id": failed_task_data["task_id"],
            "dlq_record_id": str(failed_task.id),
        }

    except Exception as e:
        logger.critical(
            "dlq_storage_failed",
            task_id=failed_task_data.get("task_id"),
            error=str(e),
        )
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dlq_tasks.replay_failed_task")
def replay_failed_task(dlq_record_id: str) -> dict[str, str]:
    db = SessionLocal()

    try:
        from uuid import UUID

        failed_task = db.query(FailedTask).filter(FailedTask.id == UUID(dlq_record_id)).first()

        if not failed_task:
            return {"status": "error", "message": "DLQ record not found"}

        if failed_task.replayed_at:
            return {
                "status": "already_replayed",
                "replayed_at": failed_task.replayed_at.isoformat(),
                "replay_status": failed_task.replay_status or "UNKNOWN",
            }

        # Parse task arguments
        args = json.loads(failed_task.args) if failed_task.args else []
        kwargs = json.loads(failed_task.kwargs) if failed_task.kwargs else {}

        # Re-queue the original task
        logger.info(
            "dlq_task_replay_started",
            dlq_record_id=dlq_record_id,
            task_name=failed_task.task_name,
        )

        result = celery_app.send_task(
            failed_task.task_name,
            args=args,
            kwargs=kwargs,
            queue="transactions",  # Send to main queue (not DLQ)
        )

        # Mark as replayed
        failed_task.replayed_at = datetime.now(UTC)
        failed_task.replay_status = "QUEUED"
        failed_task.replay_notes = f"Replayed to queue. New task ID: {result.id}"
        db.commit()

        logger.info(
            "dlq_task_replayed",
            dlq_record_id=dlq_record_id,
            new_task_id=result.id,
        )

        return {
            "status": "replayed",
            "dlq_record_id": dlq_record_id,
            "new_task_id": result.id,
        }

    except Exception as e:
        logger.error("dlq_replay_failed", dlq_record_id=dlq_record_id, error=str(e))
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dlq_tasks.get_dlq_stats")
def get_dlq_stats() -> dict[str, Any]:
    db = SessionLocal()

    try:

        total = db.query(func.count(FailedTask.id)).scalar()

        # Failed tasks by type
        by_task = (
            db.query(FailedTask.task_name, func.count(FailedTask.id))
            .group_by(FailedTask.task_name)
            .all()
        )

        # Recent failures (last 24 hours)
        from datetime import timedelta

        yesterday = datetime.now(UTC) - timedelta(days=1)
        recent = (
            db.query(func.count(FailedTask.id)).filter(FailedTask.created_at >= yesterday).scalar()
        )

        # Un_replayed tasks
        un_replayed = (
            db.query(func.count(FailedTask.id)).filter(FailedTask.replayed_at.is_(None)).scalar()
        )

        return {
            "total_failed_tasks": total,
            "tasks_by_type": dict(by_task),
            "recent_failures_24h": recent,
            "unreplayed_tasks": un_replayed,
        }

    except Exception as e:
        logger.error("dlq_stats_failed", error=str(e))
        return {"error": str(e)}

    finally:
        db.close()
