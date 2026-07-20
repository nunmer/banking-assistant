"""Add scenarios for the expanded intent set.

Seeds rows for: transfer_own, transfer_phone, deposit_open, card_block,
card_unblock, card_limit, statement_pdf, certificate, navigation, manager.

Idempotent (ON CONFLICT (intent) DO NOTHING) so it is safe on a DB that already
has some rows. mib_method defaults to POST; every endpoint currently resolves to
the mock-mib catch-all. navigation/manager are informational — they go through
the confirm flow for now; roadmap task 11 converts them to direct replies.

Note: card_limit's confirm template shows limit_kind ("daily"/"monthly") raw;
roadmap task 9 refines it to a localized current→new display.

Revision ID: 002
Revises: 001
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_INTENTS = (
    "transfer_own", "transfer_phone", "deposit_open", "card_block",
    "card_unblock", "card_limit", "statement_pdf", "certificate",
    "navigation", "manager",
)


def upgrade() -> None:
    op.execute(
        sa.text(
            r"""
            INSERT INTO scenarios
                (intent, display_name, required_params, optional_params,
                 confirm_template, confirm_templates, mib_endpoint)
            VALUES
                ('transfer_own', 'Transfer Between Own Accounts',
                 '["from_account_kind","to_account_kind","amount"]', '[]',
                 'Перевести {amount} со счёта {from_account_kind} на счёт {to_account_kind} — подтвердить?',
                 '{"ru-RU":"Перевести {amount} со счёта {from_account_kind} на счёт {to_account_kind} — подтвердить?","kk-KZ":"{from_account_kind} шотынан {to_account_kind} шотына {amount} аудару — растайсыз ба?","en-US":"Transfer {amount} from your {from_account_kind} account to your {to_account_kind} account — confirm?"}',
                 '/transfer/own'),
                ('transfer_phone', 'Transfer by Phone',
                 '["phone","amount"]', '[]',
                 'Перевести {amount} на номер {phone} — подтвердить?',
                 '{"ru-RU":"Перевести {amount} на номер {phone} — подтвердить?","kk-KZ":"{phone} нөміріне {amount} аудару — растайсыз ба?","en-US":"Transfer {amount} to {phone} — confirm?"}',
                 '/transfer/phone'),
                ('deposit_open', 'Open Deposit',
                 '["term","amount"]', '[]',
                 'Открыть депозит на {term} мес. на сумму {amount} — подтвердить?',
                 '{"ru-RU":"Открыть депозит на {term} мес. на сумму {amount} — подтвердить?","kk-KZ":"{term} айға {amount} сомасына депозит ашу — растайсыз ба?","en-US":"Open a deposit for {term} months of {amount} — confirm?"}',
                 '/deposit/open'),
                ('card_block', 'Block Card',
                 '["card_last4"]', '["card_kind"]',
                 'Заблокировать карту •• {card_last4} — подтвердить?',
                 '{"ru-RU":"Заблокировать карту •• {card_last4} — подтвердить?","kk-KZ":"•• {card_last4} картасын бұғаттау — растайсыз ба?","en-US":"Block card •• {card_last4} — confirm?"}',
                 '/card/block'),
                ('card_unblock', 'Unblock Card',
                 '["card_last4"]', '["card_kind"]',
                 'Разблокировать карту •• {card_last4} — подтвердить?',
                 '{"ru-RU":"Разблокировать карту •• {card_last4} — подтвердить?","kk-KZ":"•• {card_last4} картасының бұғатын алу — растайсыз ба?","en-US":"Unblock card •• {card_last4} — confirm?"}',
                 '/card/unblock'),
                ('card_limit', 'Change Card Limit',
                 '["card_last4","limit_kind","limit_amount"]', '[]',
                 'Изменить {limit_kind} лимит карты •• {card_last4} на {limit_amount} — подтвердить?',
                 '{"ru-RU":"Изменить {limit_kind} лимит карты •• {card_last4} на {limit_amount} — подтвердить?","kk-KZ":"•• {card_last4} картасының {limit_kind} лимитін {limit_amount} етіп өзгерту — растайсыз ба?","en-US":"Change the {limit_kind} limit on card •• {card_last4} to {limit_amount} — confirm?"}',
                 '/card/limit'),
                ('statement_pdf', 'Account Statement (PDF)',
                 '["period"]', '["account_id"]',
                 'Сформировать выписку за {period} — подтвердить?',
                 '{"ru-RU":"Сформировать выписку за {period} — подтвердить?","kk-KZ":"{period} кезеңі бойынша үзінді дайындау — растайсыз ба?","en-US":"Generate a statement for {period} — confirm?"}',
                 '/statement/pdf'),
                ('certificate', 'Account Certificate',
                 '["cert_kind"]', '[]',
                 'Подготовить справку ({cert_kind}) — подтвердить?',
                 '{"ru-RU":"Подготовить справку ({cert_kind}) — подтвердить?","kk-KZ":"Анықтама дайындау ({cert_kind}) — растайсыз ба?","en-US":"Prepare a certificate ({cert_kind}) — confirm?"}',
                 '/certificate'),
                ('navigation', 'Navigation',
                 '[]', '[]',
                 'Показать навигацию по приложению — подтвердить?',
                 '{"ru-RU":"Показать навигацию по приложению — подтвердить?","kk-KZ":"Қосымша бойынша навигацияны көрсету — растайсыз ба?","en-US":"Show app navigation — confirm?"}',
                 '/navigation'),
                ('manager', 'Contact Manager',
                 '[]', '[]',
                 'Связать вас с менеджером — подтвердить?',
                 '{"ru-RU":"Связать вас с менеджером — подтвердить?","kk-KZ":"Сізді менеджермен байланыстыру — растайсыз ба?","en-US":"Connect you with a manager — confirm?"}',
                 '/manager')
            ON CONFLICT (intent) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM scenarios WHERE intent IN :intents"
        ).bindparams(sa.bindparam("intents", _NEW_INTENTS, expanding=True))
    )
