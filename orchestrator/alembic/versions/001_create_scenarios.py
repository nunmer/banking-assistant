"""Create scenarios table.

Revision ID: 001
Revises:
Create Date: 2026-06-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent", sa.String(64), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_params", JSONB(), nullable=False, server_default="[]"),
        sa.Column("optional_params", JSONB(), nullable=False, server_default="[]"),
        sa.Column("confirm_template", sa.Text(), nullable=False),
        sa.Column("confirm_templates", JSONB(), nullable=False, server_default="{}"),
        sa.Column("mib_endpoint", sa.String(256), nullable=False),
        sa.Column("mib_method", sa.String(8), nullable=False, server_default="POST"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.execute(
        sa.text(
            r"""
            INSERT INTO scenarios
                (intent, display_name, required_params, optional_params,
                 confirm_template, confirm_templates, mib_endpoint)
            VALUES
                ('transfer', 'Money Transfer',
                 '["amount","currency","to_account"]', '[]',
                 'Перевести {amount} {currency} на счёт {to_account} — подтвердить?',
                 '{"ru-RU":"Перевести {amount} {currency} на счёт {to_account} — подтвердить?","kk-KZ":"{to_account} шотына {amount} {currency} аудару — растайсыз ба?","en-US":"Transfer {amount} {currency} to account {to_account} — confirm?"}',
                 '/transfer'),
                ('balance', 'Account Balance',
                 '[]', '[]',
                 'Узнать баланс счёта — подтвердить?',
                 '{"ru-RU":"Узнать баланс счёта — подтвердить?","kk-KZ":"Шот балансын білу — растайсыз ба?","en-US":"Retrieve your account balance — confirm?"}',
                 '/balance'),
                ('payment', 'Bill Payment',
                 '["bill_id","amount"]', '[]',
                 'Оплатить счёт {bill_id} на сумму {amount} — подтвердить?',
                 '{"ru-RU":"Оплатить счёт {bill_id} на сумму {amount} — подтвердить?","kk-KZ":"{bill_id} шотын {amount} сомасына төлеу — растайсыз ба?","en-US":"Pay bill {bill_id} for {amount} — confirm?"}',
                 '/payment'),
                ('statement', 'Transaction Statement',
                 '[]', '["limit"]',
                 'Показать последние транзакции — подтвердить?',
                 '{"ru-RU":"Показать последние транзакции — подтвердить?","kk-KZ":"Соңғы транзакцияларды көрсету — растайсыз ба?","en-US":"Show your last transactions — confirm?"}',
                 '/statement')
            ON CONFLICT (intent) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("scenarios")
