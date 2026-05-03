import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import get_settings
from app.db.repo import get_or_create_user
from app.db.session import open_connection
from app.keyboards.reply import admin_menu, main_menu
from app.texts import MAIN_MENU_TEXT, SHOP_COMING_SOON

router = Router()
BOT_MENTION_RE = re.compile(r'@([A-Za-z0-9_]{4,32})')


def _chat_matches_target(message: Message, raw_target: str) -> bool:
    target = (raw_target or '').strip()
    if not target:
        return True
    chat_id_str = str(message.chat.id)
    chat_username = (message.chat.username or '').lower()
    chat_title = (message.chat.title or '').strip().lower()
    normalized = target.lower()
    if normalized == chat_id_str:
        return True
    if normalized.startswith('@'):
        normalized = normalized[1:]
    if chat_username and normalized == chat_username:
        return True
    if chat_title and normalized == chat_title:
        return True
    return False


@router.message(F.text == '/start')
async def start_handler(message: Message, session):
    await get_or_create_user(session, message.from_user.id, message.from_user.username)
    settings = get_settings()
    is_admin = message.from_user.id in set(settings.admin_ids + settings.superadmin_ids)
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu(is_admin=is_admin))


@router.message(F.text == '🏪 Shop')
async def shop_handler(message: Message):
    await message.answer(SHOP_COMING_SOON)


@router.message(F.text == '🛡 Admin Panel')
async def admin_panel_open(message: Message, state: FSMContext):
    await state.clear()
    settings = get_settings()
    is_admin = message.from_user.id in set(settings.superadmin_ids)
    if not is_admin:
        conn = await open_connection()
        try:
            cur = await conn.execute('SELECT tg_id FROM admin_users WHERE tg_id=?', (message.from_user.id,))
            is_admin = bool(await cur.fetchone())
        finally:
            await conn.close()
    if not is_admin:
        await message.answer('Access denied.')
        return
    await message.answer('Admin panel opened.', reply_markup=admin_menu())


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_monitor(message: Message):
    text = (message.text or message.caption or '').strip()
    if not text:
        return
    conn = await open_connection()
    try:
        cur = await conn.execute("SELECT value FROM settings WHERE key='monitor_chat'")
        row = await cur.fetchone()
        monitor_chat = row['value'] if row else ''
    finally:
        await conn.close()
    if str(monitor_chat).strip() == '0':
        return
    if not _chat_matches_target(message, monitor_chat):
        return
    # auto-enforce banned users in monitored chat
    if message.from_user:
        conn2 = await open_connection()
        try:
            cur2 = await conn2.execute('SELECT is_banned, ban_reason FROM users WHERE tg_id=?', (message.from_user.id,))
            u = await cur2.fetchone()
        finally:
            await conn2.close()
        if u and u['is_banned']:
            try:
                await message.bot.ban_chat_member(chat_id=message.chat.id, user_id=message.from_user.id)
            except Exception:
                pass
            await message.answer(
                f"🚫 User @{message.from_user.username or message.from_user.id} has been banned.\nReason: {u['ban_reason'] or 'No reason provided.'}"
            )
            return

    me = await message.bot.get_me()
    my_username = (me.username or '').lower()
    found = [m.group(1) for m in BOT_MENTION_RE.finditer(text)]
    foreign_bot_mentions = []
    for username in found:
        uname = username.lower()
        if uname == my_username:
            continue
        if uname.endswith('bot') or uname.endswith('robot'):
            foreign_bot_mentions.append(username)

    author_ref = f"@{message.from_user.username}" if message.from_user and message.from_user.username else f"user {message.from_user.id if message.from_user else ''}"
    if foreign_bot_mentions:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(f"{author_ref}, mentioning third-party bots is not allowed in this chat.")
        return

    # if our bot is mentioned directly, stay silent
    if my_username and my_username in {x.lower() for x in found}:
        return

    # for any other message in monitored chat, suggest escrow bot in reply
    if me.username:
        await message.answer(
            f"Use the Escrow @{me.username}",
            reply_to_message_id=message.message_id,
        )
