from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "ee2485ef5ac1"
down_revision: Union[str, None] = "1a7fe3d4f83c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_unique_idempotency_key",
        "transactions",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_index(
        "idx_status_created_desc", "transactions", ["status", sa.text("created_at DESC")]
    )

    op.create_index(
        "idx_account_created_desc", "transactions", ["account_id", sa.text("created_at DESC")]
    )

    op.create_index("idx_created_desc", "transactions", [sa.text("created_at DESC")])

    op.create_index("idx_type_status", "transactions", ["transaction_type", "status"])


def downgrade() -> None:
    op.drop_index("idx_type_status", table_name="transactions")
    op.drop_index("idx_created_desc", table_name="transactions")
    op.drop_index("idx_account_created_desc", table_name="transactions")
    op.drop_index("idx_status_created_desc", table_name="transactions")
    op.drop_index("idx_unique_idempotency_key", table_name="transactions")
