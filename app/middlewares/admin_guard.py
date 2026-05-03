from aiogram.filters import BaseFilter

from app.config import get_settings
from app.db.session import open_connection


class AdminFilter(BaseFilter):
    async def __call__(self, event) -> bool:
        settings = get_settings()
        user = getattr(event, 'from_user', None)
        if not user:
            return False
        if user.id in set(settings.superadmin_ids):
            return True
        conn = await open_connection()
        try:
            cur = await conn.execute('SELECT tg_id FROM admin_users WHERE tg_id=?', (user.id,))
            row = await cur.fetchone()
            return bool(row)
        finally:
            await conn.close()
