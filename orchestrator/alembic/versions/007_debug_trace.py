"""Per-turn debug trace + Telegram identity for admin search.

Adds `messages.turn_id` (correlates a transcript row to its debug events),
a new `debug_events` table (one row per pipeline step: stt/classify/
extract_param/enrich/mib_execute/tts), and `session_identities` (Telegram
@username/first_name per session, upserted from /chat, so the admin panel
can search sessions by human identity instead of a bare numeric id).

Revision ID: 007
Revises: 006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("turn_id", sa.String(64), nullable=True))
    op.create_index("ix_messages_turn_id", "messages", ["turn_id"])

    op.create_table(
        "debug_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("turn_id", sa.String(64), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_debug_events_session_id", "debug_events", ["session_id"])
    op.create_index("ix_debug_events_turn_id", "debug_events", ["turn_id"])
    op.create_index("ix_debug_events_created_at", "debug_events", ["created_at"])

    op.create_table(
        "session_identities",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_session_identities_username", "session_identities", ["username"])


def downgrade() -> None:
    op.drop_index("ix_session_identities_username", table_name="session_identities")
    op.drop_table("session_identities")

    op.drop_index("ix_debug_events_created_at", table_name="debug_events")
    op.drop_index("ix_debug_events_turn_id", table_name="debug_events")
    op.drop_index("ix_debug_events_session_id", table_name="debug_events")
    op.drop_table("debug_events")

    op.drop_index("ix_messages_turn_id", table_name="messages")
    op.drop_column("messages", "turn_id")
