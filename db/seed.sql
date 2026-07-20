-- Scenario catalogue: schema + seed data.
-- Mounted into postgres via docker-entrypoint-initdb.d on first boot.

CREATE TABLE IF NOT EXISTS scenarios (
    id               SERIAL PRIMARY KEY,
    intent           VARCHAR(64) UNIQUE NOT NULL,
    display_name     VARCHAR(128) NOT NULL,
    description      TEXT,
    required_params  JSONB NOT NULL DEFAULT '[]',
    optional_params  JSONB NOT NULL DEFAULT '[]',
    -- Default confirm message (Russian).  Used as fallback when a lang-specific
    -- entry is missing from confirm_templates.
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
    (
        'transfer',
        'Money Transfer',
        '["amount", "currency", "to_account"]',
        '[]',
        'Перевести {amount} {currency} на счёт {to_account} — подтвердить?',
        '{
            "ru-RU": "Перевести {amount} {currency} на счёт {to_account} — подтвердить?",
            "kk-KZ": "{to_account} шотына {amount} {currency} аудару — растайсыз ба?",
            "en-US": "Transfer {amount} {currency} to account {to_account} — confirm?"
        }',
        '/transfer'
    ),
    (
        'balance',
        'Account Balance',
        '[]',
        '[]',
        'Узнать баланс счёта — подтвердить?',
        '{
            "ru-RU": "Узнать баланс счёта — подтвердить?",
            "kk-KZ": "Шот балансын білу — растайсыз ба?",
            "en-US": "Retrieve your account balance — confirm?"
        }',
        '/balance'
    ),
    (
        'payment',
        'Bill Payment',
        '["bill_id", "amount"]',
        '[]',
        'Оплатить счёт {bill_id} на сумму {amount} — подтвердить?',
        '{
            "ru-RU": "Оплатить счёт {bill_id} на сумму {amount} — подтвердить?",
            "kk-KZ": "{bill_id} шотын {amount} сомасына төлеу — растайсыз ба?",
            "en-US": "Pay bill {bill_id} for {amount} — confirm?"
        }',
        '/payment'
    ),
    (
        'statement',
        'Transaction Statement',
        '[]',
        '["limit"]',
        'Показать последние транзакции — подтвердить?',
        '{
            "ru-RU": "Показать последние транзакции — подтвердить?",
            "kk-KZ": "Соңғы транзакцияларды көрсету — растайсыз ба?",
            "en-US": "Show your last transactions — confirm?"
        }',
        '/statement'
    )
ON CONFLICT (intent) DO NOTHING;

-- Expanded intent set (kept in sync with alembic 002_add_scenarios).
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
ON CONFLICT (intent) DO NOTHING;
