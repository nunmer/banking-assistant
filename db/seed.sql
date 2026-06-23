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
