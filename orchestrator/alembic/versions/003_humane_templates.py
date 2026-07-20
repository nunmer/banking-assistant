"""Warmer, more conversational confirmation wording for every scenario.

Rewrites confirm_template (ru default) and confirm_templates (per-language) so
the bot reads naturally ("Перевожу 100 тенге на счёт …. Подтверждаете?") instead
of the terse "…— подтвердить?". Currency/enum placeholders are localised to
words at render time (orchestrator.services.speechtext), so KZT is shown and
spoken as "тенге".

Revision ID: 003
Revises: 002
Create Date: 2026-07-20
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# intent -> per-language confirmation wording.
TEMPLATES: dict[str, dict[str, str]] = {
    "transfer": {
        "ru-RU": "Перевожу {amount} {currency} на счёт {to_account}. Подтверждаете?",
        "kk-KZ": "{to_account} шотына {amount} {currency} аударамын. Растайсыз ба?",
        "en-US": "I'll transfer {amount} {currency} to account {to_account}. Shall I go ahead?",
    },
    "balance": {
        "ru-RU": "Показать баланс вашего счёта?",
        "kk-KZ": "Шотыңыздың балансын көрсетейін бе?",
        "en-US": "Show your account balance?",
    },
    "payment": {
        "ru-RU": "Оплачиваю счёт {bill_id} на сумму {amount}. Подтверждаете?",
        "kk-KZ": "{bill_id} шотын {amount} сомасына төлеймін. Растайсыз ба?",
        "en-US": "I'll pay bill {bill_id} for {amount}. Shall I go ahead?",
    },
    "statement": {
        "ru-RU": "Показать последние операции по счёту?",
        "kk-KZ": "Шот бойынша соңғы операцияларды көрсетейін бе?",
        "en-US": "Show your recent account activity?",
    },
    "transfer_own": {
        "ru-RU": "Перевожу {amount} между вашими счетами: {from_account_kind} → {to_account_kind}. Подтверждаете?",
        "kk-KZ": "Шоттарыңыз арасында {amount} аударамын: {from_account_kind} → {to_account_kind}. Растайсыз ба?",
        "en-US": "I'll move {amount} between your accounts: {from_account_kind} → {to_account_kind}. Shall I go ahead?",
    },
    "transfer_phone": {
        "ru-RU": "Перевожу {amount} на номер {phone}. Подтверждаете?",
        "kk-KZ": "{phone} нөміріне {amount} аударамын. Растайсыз ба?",
        "en-US": "I'll transfer {amount} to {phone}. Shall I go ahead?",
    },
    "deposit_open": {
        "ru-RU": "Открываю депозит на {term} мес. на сумму {amount}. Подтверждаете?",
        "kk-KZ": "{term} айға {amount} сомасына депозит ашамын. Растайсыз ба?",
        "en-US": "I'll open a {term}-month deposit for {amount}. Shall I go ahead?",
    },
    "card_block": {
        "ru-RU": "Блокирую карту •• {card_last4}. Подтверждаете?",
        "kk-KZ": "•• {card_last4} картасын бұғаттаймын. Растайсыз ба?",
        "en-US": "I'll block card •• {card_last4}. Shall I go ahead?",
    },
    "card_unblock": {
        "ru-RU": "Разблокирую карту •• {card_last4}. Подтверждаете?",
        "kk-KZ": "•• {card_last4} картасының бұғатын аламын. Растайсыз ба?",
        "en-US": "I'll unblock card •• {card_last4}. Shall I go ahead?",
    },
    "card_limit": {
        "ru-RU": "Меняю {limit_kind} лимит карты •• {card_last4} на {limit_amount}. Подтверждаете?",
        "kk-KZ": "•• {card_last4} картасының {limit_kind} лимитін {limit_amount} етіп өзгертемін. Растайсыз ба?",
        "en-US": "I'll change the {limit_kind} limit on card •• {card_last4} to {limit_amount}. Shall I go ahead?",
    },
    "statement_pdf": {
        "ru-RU": "Готовлю выписку за {period}. Подтверждаете?",
        "kk-KZ": "{period} бойынша үзінді дайындаймын. Растайсыз ба?",
        "en-US": "I'll prepare a statement for {period}. Shall I go ahead?",
    },
    "certificate": {
        "ru-RU": "Готовлю справку ({cert_kind}). Подтверждаете?",
        "kk-KZ": "Анықтама дайындаймын ({cert_kind}). Растайсыз ба?",
        "en-US": "I'll prepare a certificate ({cert_kind}). Shall I go ahead?",
    },
    "navigation": {
        "ru-RU": "Подсказать, как это сделать в приложении?",
        "kk-KZ": "Мұны қосымшада қалай істеу керегін көрсетейін бе?",
        "en-US": "Want me to show you how to do this in the app?",
    },
    "manager": {
        "ru-RU": "Соединить вас с менеджером?",
        "kk-KZ": "Сізді менеджермен байланыстырайын ба?",
        "en-US": "Shall I connect you with a manager?",
    },
}


def upgrade() -> None:
    conn = op.get_bind()
    stmt = sa.text(
        "UPDATE scenarios SET confirm_template = :ru, "
        "confirm_templates = CAST(:tpl AS jsonb) WHERE intent = :intent"
    )
    for intent, tpl in TEMPLATES.items():
        conn.execute(
            stmt,
            {"ru": tpl["ru-RU"], "tpl": json.dumps(tpl, ensure_ascii=False), "intent": intent},
        )


def downgrade() -> None:
    # Confirmation wording is cosmetic; the previous text is recoverable from
    # migrations 001/002 if ever needed. No-op downgrade.
    pass
