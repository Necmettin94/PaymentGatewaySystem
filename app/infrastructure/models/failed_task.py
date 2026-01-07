from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import BaseModel


class FailedTask(BaseModel):
    __tablename__ = "failed_tasks"

    # Task identification
    task_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, unique=True, comment="Original Celery task ID"
    )
    task_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Celery task name (e.g., 'process_deposit')",
    )

    # Task arguments for replay
    args: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON serialized task args"
    )
    kwargs: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON serialized task kwargs"
    )

    # Error details
    exception_type: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Exception class name"
    )
    exception_message: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Exception message"
    )
    traceback: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full exception traceback for debugging"
    )

    # Metadata
    retry_count: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Retry attempts (e.g., '3/3')"
    )
    failed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, comment="When the task originally failed"
    )

    # Replay tracking
    replayed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="When the task was replayed"
    )
    replay_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Replay result: SUCCESS, FAILED, QUEUED, SKIPPED"
    )
    replay_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Notes about replay attempt"
    )

    def __repr__(self) -> str:
        return (
            f"<FailedTask(id={self.id}, task_name={self.task_name}, "
            f"failed_at={self.failed_at}, replayed={self.replayed_at is not None})>"
        )
