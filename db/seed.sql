-- Scenario catalogue: schema + seed data (snapshot of alembic 001–005).

-- Executed-operation history (alembic 005). Written at execution time from
-- both confirm paths; read by the Mini App / web history view. session_id for
-- Telegram-authenticated users is the Telegram user id — one shared history.
CREATE TABLE IF NOT EXISTS operations (
    id         SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    intent     VARCHAR(64) NOT NULL,
    summary    TEXT NOT NULL,
    lang       VARCHAR(8) NOT NULL DEFAULT 'ru-RU',
    status     VARCHAR(16) NOT NULL,
    tx_id      VARCHAR(64) NOT NULL DEFAULT '',
    channel    VARCHAR(16) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_operations_session_id ON operations (session_id);
-- NOTE: not mounted at runtime — Alembic owns schema/seed (the orchestrator runs
-- `alembic upgrade head` on startup). Kept in sync as a readable reference.

CREATE TABLE IF NOT EXISTS scenarios (
    id               SERIAL PRIMARY KEY,
    intent           VARCHAR(64) UNIQUE NOT NULL,
    display_name     VARCHAR(128) NOT NULL,
    description      TEXT,
    required_params  JSONB NOT NULL DEFAULT '[]',
    optional_params  JSONB NOT NULL DEFAULT '[]',
    -- Default confirm message (Russian). Fallback when a lang-specific entry is
    -- missing from confirm_templates. Currency/enum placeholders are localised
    -- to words at render time (KZT → тенге).
    confirm_template TEXT NOT NULL,
    -- Per-language confirm messages keyed by BCP-47 tag (kk-KZ, ru-RU, en-US).
    confirm_templates JSONB NOT NULL DEFAULT '{}',
    mib_endpoint     VARCHAR(256) NOT NULL,
    mib_method       VARCHAR(8) NOT NULL DEFAULT 'POST',
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO scenarios
    (intent, display_name, required_params, optional_params,
     confirm_template, confirm_templates, mib_endpoint)
VALUES
    ('transfer', 'Money Transfer',
     '["amount","currency","to_account"]', '[]',
     'Перевожу {amount} {currency} на счёт {to_account}. Подтверждаете?',
     '{"ru-RU":"Перевожу {amount} {currency} на счёт {to_account}. Подтверждаете?","kk-KZ":"{to_account} шотына {amount} {currency} аударамын. Растайсыз ба?","en-US":"I''ll transfer {amount} {currency} to account {to_account}. Shall I go ahead?"}',
     '/transfer'),
    ('balance', 'Account Balance',
     '[]', '[]',
     'Показать баланс вашего счёта?',
     '{"ru-RU":"Показать баланс вашего счёта?","kk-KZ":"Шотыңыздың балансын көрсетейін бе?","en-US":"Show your account balance?"}',
     '/balance'),
    ('payment', 'Bill Payment',
     '["bill_id","amount"]', '[]',
     'Оплачиваю счёт {bill_id} на сумму {amount}. Подтверждаете?',
     '{"ru-RU":"Оплачиваю счёт {bill_id} на сумму {amount}. Подтверждаете?","kk-KZ":"{bill_id} шотын {amount} сомасына төлеймін. Растайсыз ба?","en-US":"I''ll pay bill {bill_id} for {amount}. Shall I go ahead?"}',
     '/payment'),
    ('statement', 'Transaction Statement',
     '[]', '["limit"]',
     'Показать последние операции по счёту?',
     '{"ru-RU":"Показать последние операции по счёту?","kk-KZ":"Шот бойынша соңғы операцияларды көрсетейін бе?","en-US":"Show your recent account activity?"}',
     '/statement'),
    ('transfer_own', 'Transfer Between Own Accounts',
     '["from_account_kind","to_account_kind","amount"]', '[]',
     'Перевожу {amount} со счёта «{from_account_name}» на счёт «{to_account_name}». Подтверждаете?',
     '{"ru-RU":"Перевожу {amount} со счёта «{from_account_name}» на счёт «{to_account_name}». Подтверждаете?","kk-KZ":"«{from_account_name}» шотынан «{to_account_name}» шотына {amount} аударамын. Растайсыз ба?","en-US":"I''ll transfer {amount} from your {from_account_name} account to your {to_account_name} account. Shall I go ahead?"}',
     '/transfer/own'),
    ('transfer_phone', 'Transfer by Phone',
     '["phone","amount"]', '[]',
     'Перевожу {amount} на номер {phone}. Подтверждаете?',
     '{"ru-RU":"Перевожу {amount} на номер {phone}. Подтверждаете?","kk-KZ":"{phone} нөміріне {amount} аударамын. Растайсыз ба?","en-US":"I''ll transfer {amount} to {phone}. Shall I go ahead?"}',
     '/transfer/phone'),
    ('deposit_open', 'Open Deposit',
     '["term","amount"]', '[]',
     'Открываю депозит на {term} мес. на сумму {amount}. Подтверждаете?',
     '{"ru-RU":"Открываю депозит на {term} мес. на сумму {amount}. Подтверждаете?","kk-KZ":"{term} айға {amount} сомасына депозит ашамын. Растайсыз ба?","en-US":"I''ll open a {term}-month deposit for {amount}. Shall I go ahead?"}',
     '/deposit/open'),
    ('card_block', 'Block Card',
     '["card_last4"]', '["card_kind"]',
     'Блокирую карту •• {card_last4}. Подтверждаете?',
     '{"ru-RU":"Блокирую карту •• {card_last4}. Подтверждаете?","kk-KZ":"•• {card_last4} картасын бұғаттаймын. Растайсыз ба?","en-US":"I''ll block card •• {card_last4}. Shall I go ahead?"}',
     '/card/block'),
    ('card_unblock', 'Unblock Card',
     '["card_last4"]', '["card_kind"]',
     'Разблокирую карту •• {card_last4}. Подтверждаете?',
     '{"ru-RU":"Разблокирую карту •• {card_last4}. Подтверждаете?","kk-KZ":"•• {card_last4} картасының бұғатын аламын. Растайсыз ба?","en-US":"I''ll unblock card •• {card_last4}. Shall I go ahead?"}',
     '/card/unblock'),
    ('card_limit', 'Change Card Limit',
     '["card_last4","limit_kind","limit_amount"]', '[]',
     'Меняю {limit_kind} лимит карты •• {card_last4} на {limit_amount}. Подтверждаете?',
     '{"ru-RU":"Меняю {limit_kind} лимит карты •• {card_last4} на {limit_amount}. Подтверждаете?","kk-KZ":"•• {card_last4} картасының {limit_kind} лимитін {limit_amount} етіп өзгертемін. Растайсыз ба?","en-US":"I''ll change the {limit_kind} limit on card •• {card_last4} to {limit_amount}. Shall I go ahead?"}',
     '/card/limit'),
    ('statement_pdf', 'Account Statement (PDF)',
     '["period"]', '["account_id"]',
     'Готовлю выписку за {period}. Подтверждаете?',
     '{"ru-RU":"Готовлю выписку за {period}. Подтверждаете?","kk-KZ":"{period} бойынша үзінді дайындаймын. Растайсыз ба?","en-US":"I''ll prepare a statement for {period}. Shall I go ahead?"}',
     '/statement/pdf'),
    ('certificate', 'Account Certificate',
     '["cert_kind"]', '[]',
     'Готовлю справку ({cert_kind}). Подтверждаете?',
     '{"ru-RU":"Готовлю справку ({cert_kind}). Подтверждаете?","kk-KZ":"Анықтама дайындаймын ({cert_kind}). Растайсыз ба?","en-US":"I''ll prepare a certificate ({cert_kind}). Shall I go ahead?"}',
     '/certificate'),
    ('navigation', 'Navigation',
     '[]', '[]',
     'Подсказать, как это сделать в приложении?',
     '{"ru-RU":"Подсказать, как это сделать в приложении?","kk-KZ":"Мұны қосымшада қалай істеу керегін көрсетейін бе?","en-US":"Want me to show you how to do this in the app?"}',
     '/navigation'),
    ('manager', 'Contact Manager',
     '[]', '[]',
     'Соединить вас с менеджером?',
     '{"ru-RU":"Соединить вас с менеджером?","kk-KZ":"Сізді менеджермен байланыстырайын ба?","en-US":"Shall I connect you with a manager?"}',
     '/manager')
ON CONFLICT (intent) DO NOTHING;
