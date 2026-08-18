"""Fix mispronounced deposit term unit in the Russian confirm template.

`deposit_open`'s ru-RU template hardcoded the abbreviation "мес." next to
{term} (e.g. "Открываю депозит на 7 мес."). Yandex TTS reads that
abbreviation close to literally ("7 mios"), not expanded to the real word —
the same class of bug already fixed for "period" (see speechtext.py's
_RU_DURATION_FORMS), but "term" bypassed that module entirely since the unit
word was static template text, not a rendered param. Switches the template
to a new {term_unit} placeholder, derived at render time by
speechtext.py's for_display/for_speech (abbreviated "мес." for display,
correctly-declined for speech). kk-KZ/en-US are already grammatically
correct for any count as static text ("{term} айға", "{term}-month") and are
left unchanged — str.format silently ignores the unused {term_unit} kwarg
for those.

Revision ID: 008
Revises: 007
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RU_TEMPLATE = "Открываю депозит на {term} {term_unit} на сумму {amount}. Подтверждаете?"
_KK_TEMPLATE = "{term} айға {amount} сомасына депозит ашамын. Растайсыз ба?"
_EN_TEMPLATE = "I'll open a {term}-month deposit for {amount}. Shall I go ahead?"


def upgrade() -> None:
    conn = op.get_bind()
    tpl = {"ru-RU": _RU_TEMPLATE, "kk-KZ": _KK_TEMPLATE, "en-US": _EN_TEMPLATE}
    conn.execute(
        sa.text(
            "UPDATE scenarios SET confirm_template = :ru, "
            "confirm_templates = CAST(:tpl AS jsonb) WHERE intent = :intent"
        ),
        {"ru": _RU_TEMPLATE, "tpl": json.dumps(tpl, ensure_ascii=False), "intent": "deposit_open"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    tpl = {
        "ru-RU": "Открываю депозит на {term} мес. на сумму {amount}. Подтверждаете?",
        "kk-KZ": _KK_TEMPLATE,
        "en-US": _EN_TEMPLATE,
    }
    conn.execute(
        sa.text(
            "UPDATE scenarios SET confirm_template = :ru, "
            "confirm_templates = CAST(:tpl AS jsonb) WHERE intent = :intent"
        ),
        {"ru": tpl["ru-RU"], "tpl": json.dumps(tpl, ensure_ascii=False), "intent": "deposit_open"},
    )
