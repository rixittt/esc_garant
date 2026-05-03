from decimal import Decimal

from app.db.repo import fetchall, fetchone


async def get_value(conn, key: str, fallback: str | None = None) -> str | None:
    row = await fetchone(conn, 'SELECT value FROM settings WHERE key=?', (key,))
    return row['value'] if row else fallback


async def set_value(conn, key: str, value: str) -> None:
    await conn.execute(
        'INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
        (key, value),
    )


async def get_decimal(conn, key: str, fallback: Decimal) -> Decimal:
    value = await get_value(conn, key)
    return Decimal(value) if value is not None else fallback


async def list_settings(conn) -> list[dict]:
    return await fetchall(conn, 'SELECT key, value FROM settings ORDER BY key')
