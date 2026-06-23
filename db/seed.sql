-- Scenario catalogue: schema + seed data.
-- Mounted into postgres via docker-entrypoint-initdb.d on first boot.

CREATE TABLE IF NOT EXISTS scenarios (
    id               SERIAL PRIMARY KEY,
    intent           VARCHAR(64) UNIQUE NOT NULL,
    display_name     VARCHAR(128) NOT NULL,
    description      TEXT,
    required_params  JSONB NOT NULL DEFAULT '[]',
    optional_params  JSONB NOT NULL DEFAULT '[]',
    confirm_template TEXT NOT NULL,
    mib_endpoint     VARCHAR(256) NOT NULL,
    mib_method       VARCHAR(8) NOT NULL DEFAULT 'POST',
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO scenarios
    (intent, display_name, required_params, optional_params, confirm_template, mib_endpoint)
VALUES
    (
        'transfer',
        'Money Transfer',
        '["amount", "currency", "to_account"]',
        '[]',
        'Transfer {amount} {currency} to account {to_account} — confirm?',
        '/transfer'
    ),
    (
        'balance',
        'Account Balance',
        '[]',
        '[]',
        'Retrieve your account balance — confirm?',
        '/balance'
    ),
    (
        'payment',
        'Bill Payment',
        '["bill_id", "amount"]',
        '[]',
        'Pay bill {bill_id} for {amount} — confirm?',
        '/payment'
    ),
    (
        'statement',
        'Transaction Statement',
        '[]',
        '["limit"]',
        'Show your last transactions — confirm?',
        '/statement'
    )
ON CONFLICT (intent) DO NOTHING;
