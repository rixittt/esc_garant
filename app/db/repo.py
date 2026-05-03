from typing import Any


async def fetchone(conn, query: str, params: tuple = ()) -> dict[str, Any] | None:
    cur = await conn.execute(query, params)
    row = await cur.fetchone()
    return dict(row) if row else None


async def fetchall(conn, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    cur = await conn.execute(query, params)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_or_create_user(conn, tg_id: int, username: str | None) -> dict:
    user = await fetchone(conn, 'SELECT * FROM users WHERE tg_id=?', (tg_id,))
    if user:
        if user.get('username') != username:
            await conn.execute('UPDATE users SET username=? WHERE id=?', (username, user['id']))
            user['username'] = username
        return user

    await conn.execute('INSERT INTO users(tg_id, username) VALUES(?, ?)', (tg_id, username))
    user = await fetchone(conn, 'SELECT * FROM users WHERE tg_id=?', (tg_id,))
    await conn.execute('INSERT INTO wallets(user_id, available_balance, frozen_balance) VALUES(?, 0, 0)', (user['id'],))
    return user


async def get_user_by_tg_id(conn, tg_id: int) -> dict | None:
    return await fetchone(conn, 'SELECT * FROM users WHERE tg_id=?', (tg_id,))
