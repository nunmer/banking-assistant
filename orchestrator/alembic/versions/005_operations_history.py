"""Operation history table — durable record of executed operations.

Recorded at execution time (both the chat "да" path and the confirm-button
path), listed by the Mini App / web UI, and shared across channels because
Telegram-authenticated web sessions use the Telegram user id as session_id.

Revision ID: 005
Revises: 004
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("lang", sa.String(8), nullable=False, server_default="ru-RU"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("tx_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("channel", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_operations_session_id", "operations", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_session_id", table_name="operations")
    op.drop_table("operations")
