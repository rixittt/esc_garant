import asyncio

from app.db.session import open_connection

SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    is_banned INTEGER NOT NULL DEFAULT 0,
    ban_reason TEXT,
    banned_by INTEGER,
    banned_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id INTEGER PRIMARY KEY,
    available_balance NUMERIC NOT NULL DEFAULT 0,
    frozen_balance NUMERIC NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT UNIQUE NOT NULL,
    buyer_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    amount NUMERIC NOT NULL,
    terms TEXT NOT NULL,
    status TEXT NOT NULL,
    complete_requested_by INTEGER,
    cancel_requested_by INTEGER,
    buyer_confirmed INTEGER NOT NULL DEFAULT 0,
    seller_confirmed INTEGER NOT NULL DEFAULT 0,
    buyer_cancel_confirmed INTEGER NOT NULL DEFAULT 0,
    seller_cancel_confirmed INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS deal_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS disputes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER UNIQUE NOT NULL,
    opened_by INTEGER NOT NULL,
    reason_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    resolution_type TEXT,
    resolved_by INTEGER,
    resolved_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dispute_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    text TEXT,
    attachments_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    invoice_id INTEGER UNIQUE NOT NULL,
    amount_usd NUMERIC NOT NULL,
    pay_url TEXT NOT NULL,
    notify_chat_id INTEGER,
    notify_message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    credited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS withdraw_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount NUMERIC NOT NULL,
    fee_percent NUMERIC NOT NULL,
    fee_amount NUMERIC NOT NULL,
    net_amount NUMERIC NOT NULL,
    requisites TEXT NOT NULL,
    status TEXT NOT NULL,
    tx_info TEXT,
    processed_by INTEGER,
    processed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER UNIQUE NOT NULL,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_users (
    tg_id INTEGER PRIMARY KEY,
    granted_by INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
'''


DEFAULT_SETTINGS = {
    'withdraw_fee_percent': '0',
    'withdraw_fee_amount': '0.50',
    'min_deal_amount': '1.00',
    'min_withdraw_amount': '4.50',
    'support_admin_username': 'admin',
    'monitor_chat': '',
}


async def init_db() -> None:
    conn = await open_connection()
    try:
        await conn.executescript(SCHEMA_SQL)
        cur = await conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reviews'")
        table_sql_row = await cur.fetchone()
        table_sql = (table_sql_row['sql'] or '').lower() if table_sql_row else ''
        if 'deal_id integer unique' in table_sql:
            await conn.executescript(
                '''
                ALTER TABLE reviews RENAME TO reviews_old;
                CREATE TABLE reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_id INTEGER NOT NULL,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(deal_id, from_user_id)
                );
                INSERT INTO reviews(id, deal_id, from_user_id, to_user_id, stars, created_at)
                SELECT id, deal_id, from_user_id, to_user_id, stars, created_at
                FROM reviews_old;
                DROP TABLE reviews_old;
                '''
            )
        deal_cols_cur = await conn.execute("PRAGMA table_info(deals)")
        deal_cols = {row['name'] for row in await deal_cols_cur.fetchall()}
        if 'cancel_requested_by' not in deal_cols:
            await conn.execute("ALTER TABLE deals ADD COLUMN cancel_requested_by INTEGER")
        if 'buyer_cancel_confirmed' not in deal_cols:
            await conn.execute("ALTER TABLE deals ADD COLUMN buyer_cancel_confirmed INTEGER NOT NULL DEFAULT 0")
        if 'seller_cancel_confirmed' not in deal_cols:
            await conn.execute("ALTER TABLE deals ADD COLUMN seller_cancel_confirmed INTEGER NOT NULL DEFAULT 0")
        user_cols_cur = await conn.execute("PRAGMA table_info(users)")
        user_cols = {row['name'] for row in await user_cols_cur.fetchall()}
        if 'ban_reason' not in user_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
        if 'banned_by' not in user_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN banned_by INTEGER")
        if 'banned_at' not in user_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")
        dep_cols_cur = await conn.execute("PRAGMA table_info(deposits)")
        dep_cols = {row['name'] for row in await dep_cols_cur.fetchall()}
        if 'notify_chat_id' not in dep_cols:
            await conn.execute("ALTER TABLE deposits ADD COLUMN notify_chat_id INTEGER")
        if 'notify_message_id' not in dep_cols:
            await conn.execute("ALTER TABLE deposits ADD COLUMN notify_message_id INTEGER")
        for key, value in DEFAULT_SETTINGS.items():
            await conn.execute('INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)', (key, value))
        await conn.commit()
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(init_db())
