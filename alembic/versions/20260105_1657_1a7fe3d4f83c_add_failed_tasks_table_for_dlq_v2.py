from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "1a7fe3d4f83c"
down_revision: Union[str, None] = "247b6a5d3afb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failed_tasks",
        sa.Column(
            "task_id", sa.String(length=255), nullable=False, comment="Original Celery task ID"
        ),
        sa.Column(
            "task_name",
            sa.String(length=255),
            nullable=False,
            comment="Celery task name (e.g., 'process_deposit')",
        ),
        sa.Column("args", sa.Text(), nullable=True, comment="JSON serialized task args"),
        sa.Column("kwargs", sa.Text(), nullable=True, comment="JSON serialized task kwargs"),
        sa.Column(
            "exception_type", sa.String(length=255), nullable=False, comment="Exception class name"
        ),
        sa.Column("exception_message", sa.Text(), nullable=False, comment="Exception message"),
        sa.Column(
            "traceback", sa.Text(), nullable=True, comment="Full exception traceback for debugging"
        ),
        sa.Column(
            "retry_count",
            sa.String(length=50),
            nullable=True,
            comment="Retry attempts (e.g., '3/3')",
        ),
        sa.Column(
            "failed_at", sa.DateTime(), nullable=False, comment="When the task originally failed"
        ),
        sa.Column(
            "replayed_at", sa.DateTime(), nullable=True, comment="When the task was replayed"
        ),
        sa.Column(
            "replay_status",
            sa.String(length=50),
            nullable=True,
            comment="Replay result: SUCCESS, FAILED, QUEUED, SKIPPED",
        ),
        sa.Column("replay_notes", sa.Text(), nullable=True, comment="Notes about replay attempt"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_failed_tasks_created_at"), "failed_tasks", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_failed_tasks_failed_at"), "failed_tasks", ["failed_at"], unique=False)
    op.create_index(op.f("ix_failed_tasks_id"), "failed_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_failed_tasks_task_id"), "failed_tasks", ["task_id"], unique=True)
    op.create_index(op.f("ix_failed_tasks_task_name"), "failed_tasks", ["task_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_failed_tasks_task_name"), table_name="failed_tasks")
    op.drop_index(op.f("ix_failed_tasks_task_id"), table_name="failed_tasks")
    op.drop_index(op.f("ix_failed_tasks_id"), table_name="failed_tasks")
    op.drop_index(op.f("ix_failed_tasks_failed_at"), table_name="failed_tasks")
    op.drop_index(op.f("ix_failed_tasks_created_at"), table_name="failed_tasks")
    op.drop_table("failed_tasks")
