import asyncio

from app.config import get_settings
from app.db.repo import fetchone
from app.db.session import open_connection


async def main() -> None:
    settings = get_settings()
    ids = set(settings.superadmin_ids)
    if not ids:
        print('No SUPERADMIN_IDS configured.')
        return

    conn = await open_connection()
    try:
        await conn.execute('CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, is_superadmin INTEGER, is_active INTEGER)')
        for tg_id in ids:
            user = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (tg_id,))
            if not user:
                print(f'User with tg_id={tg_id} not found. Ask user to run /start first.')
                continue
            await conn.execute(
                'INSERT INTO admins(user_id, is_superadmin, is_active) VALUES(?, 1, 1) ON CONFLICT(user_id) DO UPDATE SET is_superadmin=1, is_active=1',
                (user['id'],),
            )
        await conn.commit()
        print('Superadmin sync complete.')
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
