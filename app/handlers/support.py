from aiogram import F, Router
from aiogram.types import Message

from app.config import get_settings
from app.services.settings import get_value

router = Router()


@router.message(F.text == '🛠 Support')
async def support_handler(message: Message, session):
    cfg = get_settings()
    username = await get_value(session, 'support_admin_username', cfg.support_admin_username)
    clean = username.strip()
    if not clean.startswith('@'):
        clean = f'@{clean}'
    await message.answer(f'Support: {clean}')
