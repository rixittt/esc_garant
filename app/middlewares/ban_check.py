from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.db.repo import fetchone
from app.texts import BANNED


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        conn = data.get('session')
        user = data.get('event_from_user')
        if not conn or not user:
            return await handler(event, data)

        db_user = await fetchone(conn, 'SELECT is_banned FROM users WHERE tg_id=?', (user.id,))
        if db_user and db_user['is_banned'] and isinstance(event, Message):
            await event.answer(BANNED)
            return
        return await handler(event, data)
