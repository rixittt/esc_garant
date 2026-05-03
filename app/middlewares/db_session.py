from aiogram import BaseMiddleware

from app.db.session import open_connection


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        conn = await open_connection()
        try:
            data['session'] = conn
            result = await handler(event, data)
            await conn.commit()
            return result
        finally:
            await conn.close()
