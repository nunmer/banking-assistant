"""transfer_own confirms with resolved account names, not raw kind codes.

The enrichment step resolves from/to_account_kind to real accounts and adds
from/to_account_name (localised) — templates now read like a human:
"Перевожу 10000 со счёта «Тенговый» на счёт «Долларовый»".

Revision ID: 004
Revises: 003
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

NEW_TEMPLATES = {
    "ru-RU": "Перевожу {amount} со счёта «{from_account_name}» на счёт «{to_account_name}». Подтверждаете?",
    "kk-KZ": "«{from_account_name}» шотынан «{to_account_name}» шотына {amount} аударамын. Растайсыз ба?",
    "en-US": "I'll transfer {amount} from your {from_account_name} account to your {to_account_name} account. Shall I go ahead?",
}

OLD_TEMPLATES = {
    "ru-RU": "Перевожу {amount} между вашими счетами: {from_account_kind} → {to_account_kind}. Подтверждаете?",
    "kk-KZ": "Шоттарыңыз арасында {amount} аударамын: {from_account_kind} → {to_account_kind}. Растайсыз ба?",
    "en-US": "I'll move {amount} between your accounts: {from_account_kind} → {to_account_kind}. Shall I go ahead?",
}


def _set(templates: dict) -> None:
    op.execute(
        sa.text(
            "UPDATE scenarios SET confirm_templates = CAST(:tpl AS jsonb) "
            "WHERE intent = 'transfer_own'"
        ).bindparams(tpl=json.dumps(templates, ensure_ascii=False))
    )


def upgrade() -> None:
    _set(NEW_TEMPLATES)


def downgrade() -> None:
    _set(OLD_TEMPLATES)
