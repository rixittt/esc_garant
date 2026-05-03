from decimal import Decimal
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.callbacks import (
    AdminDealCb,
    AdminDealPageCb,
    AdminDisputeCb,
    AdminDisputePageCb,
    AdminDisputeTargetCb,
    AdminManageCb,
    AdminSettingCb,
    AdminTxCb,
    AdminTxPageCb,
    AdminUserCb,
    AdminWithdrawCb,
    AdminWithdrawPageCb,
    BroadcastCb,
)
from app.config import get_settings
from app.db.repo import fetchall, fetchone
from app.keyboards.inline import (
    admin_deals_list_kb,
    admin_dispute_kb,
    admin_disputes_list_kb,
    admin_user_deals_kb,
    admin_user_deposits_kb,
    manage_admin_confirm_kb,
    manage_admins_kb,
    manage_admins_remove_list_kb,
    admin_transactions_list_kb,
    admin_user_profile_kb,
    admin_withdraw_kb,
    admin_user_withdraws_kb,
    admin_withdraws_list_kb,
    broadcast_skip_photo_kb,
    dispute_target_kb,
    settings_kb,
)
from app.keyboards.reply import main_menu
from app.middlewares.admin_guard import AdminFilter
from app.services import deals as deals_service
from app.services import withdrawals
from app.services.disputes import get_dispute_by_deal, request_more_info, resolve_buyer, resolve_seller, resolve_split, resume_deal
from app.services.notifications import safe_send, safe_send_photo
from app.services.settings import list_settings, set_value
from app.states import AdminBanReasonSG, AdminDisputeMoreInfoSG, AdminManageAdminsSG, AdminSettingSG, AdminUserBalanceSG, AdminUserSearchSG, AdminWithdrawSG, BroadcastSG

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())
MENU_BUTTONS = {'💼 My Deals', '➕ Create Deal', '👤 Profile', '💰 Balance', '📤 Withdraw', '📥 Deposit', '🛠 Support', '🏪 Shop', '🛡 Admin Panel', '🔎 Find User', '📊 Users', '📂 Deals', '🌐 All Deals', '💳 Transactions', '📤 Withdraw Requests', '⚖️ Disputes', '📢 Broadcast', '⚙️ Settings', '⬅️ User Menu'}
TELEGRAM_TEXT_LIMIT = 4096


@router.callback_query(F.data == 'noop')
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.message(
    StateFilter(
        AdminUserBalanceSG.amount,
        AdminManageAdminsSG.command,
        AdminSettingSG.value,
        AdminBanReasonSG.reason,
        AdminUserSearchSG.query,
        AdminWithdrawSG.tx_info,
        AdminDisputeMoreInfoSG.target,
        AdminDisputeMoreInfoSG.text,
        BroadcastSG.text,
        BroadcastSG.photo,
    ),
    F.text.in_(MENU_BUTTONS),
)
async def interrupt_admin_fsm_by_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('Previous admin action cancelled. Menu command received.')


def _is_superadmin(tg_id: int) -> bool:
    return tg_id in set(get_settings().superadmin_ids)


def _split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT):
    if len(text) <= limit:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + limit, text_len)
        if end < text_len:
            split_at = text.rfind('\n', start, end)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end if end > start else start + limit
    return chunks or ['']


async def _send_deal_card_with_history(message: Message, deal: dict, buyer: dict, seller: dict, history: str, history_count: int, reply_markup=None):
    full_text = (
        f"📂 Deal #{deal['public_id']}\n"
        f"Status: {deal['status']}\n"
        f"Amount: ${Decimal(str(deal['amount'])):.2f}\n"
        f"Buyer: @{buyer['username'] or buyer['tg_id']}\n"
        f"Seller: @{seller['username'] or seller['tg_id']}\n"
        f"Terms: {deal['terms']}\n"
        f"Created: {deal['created_at']}\n"
        f"Updated: {deal['updated_at']}\n\n"
        f"💬 Chat history ({history_count} messages):\n{history}"
    )
    chunks = _split_message(full_text)
    for idx, chunk in enumerate(chunks):
        if idx == 0:
            await message.answer(chunk, reply_markup=reply_markup)
        else:
            await message.answer(f"(cont.)\n{chunk}")


def _render_user_profile_card(user: dict, wallet: dict, completed: dict, disputes_lost: dict, purchases: dict, sales: dict, deposits: dict, withdraws: dict) -> str:
    return (
        f"🧽 User: @{user['username'] or user['tg_id']}\n"
        f"🪪 ID: {user['tg_id']}\n"
        f"🚫 Banned: {'yes' if user['is_banned'] else 'no'}\n"
        f"🧾 Ban reason: {user.get('ban_reason') or '—'}\n"
        f"👮 Banned by: {user.get('banned_by_ref') or user.get('banned_by') or '—'}\n"
        f"🕒 Banned at: {user.get('banned_at') or '—'}\n"
        f"💵 Available: ${Decimal(str(wallet['available_balance'])):.2f}\n"
        f"🧊 Frozen: ${Decimal(str(wallet['frozen_balance'])):.2f}\n\n"
        f"🤝 Completed deals: {completed['c']}\n"
        f"⚖️ Disputes lost: {disputes_lost['c']}\n"
        f"📈 Purchases: ${Decimal(str(purchases['s'])):.2f}\n"
        f"📉 Sales: ${Decimal(str(sales['s'])):.2f}\n\n"
        f"📥 Deposits: {deposits['c']} (sum ${Decimal(str(deposits['s'])):.2f})\n"
        f"📤 Withdrawals: {withdraws['c']} (sum ${Decimal(str(withdraws['s'])):.2f})"
    )


def _render_settings_text(rows: list[dict]) -> str:
    return '\n'.join([f"{x['key']}: {x['value']}" for x in rows])


async def _send_admin_user_profile(message_or_callback, session, target_user: dict):
    if target_user.get('banned_by'):
        banner = await fetchone(session, 'SELECT username, tg_id FROM users WHERE tg_id=?', (target_user['banned_by'],))
        if banner:
            target_user['banned_by_ref'] = f"@{banner['username']}" if banner.get('username') else str(banner['tg_id'])
    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (target_user['id'],))
    completed = await fetchone(session, "SELECT COUNT(*) AS c FROM deals WHERE status='COMPLETED' AND (buyer_id=? OR seller_id=?)", (target_user['id'], target_user['id']))
    disputes_lost = await fetchone(
        session,
        "SELECT COUNT(*) AS c FROM disputes d JOIN deals x ON x.id=d.deal_id WHERE d.status='RESOLVED' AND ((d.resolution_type='BUYER' AND x.seller_id=?) OR (d.resolution_type='SELLER' AND x.buyer_id=?))",
        (target_user['id'], target_user['id']),
    )
    purchases = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE buyer_id=? AND status='COMPLETED'", (target_user['id'],))
    sales = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE seller_id=? AND status='COMPLETED'", (target_user['id'],))
    deposits = await fetchone(session, "SELECT COUNT(*) AS c, COALESCE(SUM(amount_usd),0) AS s FROM deposits WHERE user_id=? AND status='PAID' AND credited=1", (target_user['id'],))
    withdraws = await fetchone(session, "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM withdraw_requests WHERE user_id=? AND status='APPROVED'", (target_user['id'],))
    text = _render_user_profile_card(target_user, wallet, completed, disputes_lost, purchases, sales, deposits, withdraws)
    kb = admin_user_profile_kb(target_user['id'], bool(target_user['is_banned']))
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb)
    else:
        await message_or_callback.message.answer(text, reply_markup=kb)


@router.message(F.text == '⬅️ User Menu')
async def admin_back_to_user_menu(message: Message):
    await message.answer('Returned to user menu.', reply_markup=main_menu(is_admin=True))


@router.message(F.text == '🔎 Find User')
async def admin_find_user_start(message: Message, state: FSMContext):
    await state.set_state(AdminUserSearchSG.query)
    await message.answer('Enter @username or Telegram ID:')


@router.message(AdminUserSearchSG.query)
async def admin_find_user_query(message: Message, state: FSMContext, session):
    user = await deals_service.find_user_by_username_or_id(session, message.text.strip())
    if not user:
        await message.answer('User not found. Try again with valid @username or Telegram ID.')
        return
    await _send_admin_user_profile(message, session, user)
    await state.clear()


@router.message(F.text == '📊 Users')
async def admin_users_stats(message: Message, session):
    total_users = await fetchone(session, 'SELECT COUNT(*) AS c FROM users')
    banned = await fetchone(session, 'SELECT COUNT(*) AS c FROM users WHERE is_banned=1')
    deals_total = await fetchone(session, 'SELECT COUNT(*) AS c FROM deals')
    completed = await fetchone(session, "SELECT COUNT(*) AS c FROM deals WHERE status='COMPLETED'")
    deals_active = await fetchone(session, "SELECT COUNT(*) AS c FROM deals WHERE status='ACTIVE'")
    deposits_total = await fetchone(session, "SELECT COUNT(*) AS c, COALESCE(SUM(amount_usd),0) AS s FROM deposits WHERE status='PAID' AND credited=1")
    withdraw_done = await fetchone(session, "SELECT COUNT(*) AS c, COALESCE(SUM(amount),0) AS s FROM withdraw_requests WHERE status='APPROVED'")
    pending_withdraw = await fetchone(session, "SELECT COUNT(*) AS c FROM withdraw_requests WHERE status='PENDING'")

    await message.answer(
        f"📊 Users overview\n\n"
        f"Total users: {total_users['c']}\n"
        f"Banned users: {banned['c']}\n\n"
        f"Deals total: {deals_total['c']}\n"
        f"Deals active: {deals_active['c']}\n"
        f"Deals completed: {completed['c']}\n\n"
        f"Deposits credited: {deposits_total['c']} (sum ${Decimal(str(deposits_total['s'])):.2f})\n"
        f"Withdrawals approved: {withdraw_done['c']} (sum ${Decimal(str(withdraw_done['s'])):.2f})\n"
        f"Pending withdraw requests: {pending_withdraw['c']}"
    )


@router.callback_query(AdminUserCb.filter())
async def admin_user_actions(callback: CallbackQuery, callback_data: AdminUserCb, state: FSMContext, session):
    user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (callback_data.user_id,))
    if not user:
        await callback.answer('User not found.', show_alert=True)
        return

    if callback_data.action == 'refresh':
        await _send_admin_user_profile(callback, session, user)
        await callback.answer()
        return
    if callback_data.action.startswith('deals_'):
        page = max(int(callback_data.action.split('_')[1]), 1)
        page_size = 5
        offset = (page - 1) * page_size
        items = await fetchall(session, "SELECT * FROM deals WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (user['id'], user['id'], page_size, offset))
        total = await fetchone(session, "SELECT COUNT(*) AS c FROM deals WHERE buyer_id=? OR seller_id=?", (user['id'], user['id']))
        total_pages = max((total['c'] + page_size - 1) // page_size, 1)
        await callback.message.answer(f"📂 Deals for @{user['username'] or user['tg_id']}:", reply_markup=admin_user_deals_kb(user['id'], items, page, total_pages))
        await callback.answer()
        return
    if callback_data.action.startswith('deal_open_'):
        deal_id = int(callback_data.action.split('_')[-1])
        deal = await fetchone(session, 'SELECT * FROM deals WHERE id=?', (deal_id,))
        if not deal:
            await callback.answer('Deal not found.', show_alert=True)
            return
        buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
        seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
        msgs = await fetchall(session, 'SELECT * FROM deal_messages WHERE deal_id=? ORDER BY id ASC', (deal['id'],))
        history_lines = []
        for m in msgs:
            sender = buyer if m['sender_id'] == deal['buyer_id'] else seller
            sender_ref = f"@{sender['username'] or sender['tg_id']}" if sender else str(m['sender_id'])
            history_lines.append(f"{sender_ref}: {m['text'] or ''}")
        history = '\n'.join(history_lines) if history_lines else 'No messages yet.'
        await _send_deal_card_with_history(
            callback.message,
            deal,
            buyer,
            seller,
            history,
            len(msgs),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user['id']).pack())]]),
        )
        await callback.answer()
        return
    if callback_data.action.startswith('deposits_'):
        page = max(int(callback_data.action.split('_')[1]), 1)
        page_size = 5
        offset = (page - 1) * page_size
        items = await fetchall(session, "SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (user['id'], page_size, offset))
        total = await fetchone(session, "SELECT COUNT(*) AS c FROM deposits WHERE user_id=?", (user['id'],))
        total_pages = max((total['c'] + page_size - 1) // page_size, 1)
        await callback.message.answer(f"📥 Deposits for @{user['username'] or user['tg_id']}:", reply_markup=admin_user_deposits_kb(user['id'], items, page, total_pages))
        await callback.answer()
        return
    if callback_data.action.startswith('deposit_open_'):
        dep_id = int(callback_data.action.split('_')[-1])
        dep = await fetchone(session, 'SELECT * FROM deposits WHERE id=?', (dep_id,))
        if not dep:
            await callback.answer('Deposit not found.', show_alert=True)
            return
        await callback.message.answer(
            f"📥 Deposit #{dep['id']}\n"
            f"Invoice ID: {dep['invoice_id']}\n"
            f"Amount: ${Decimal(str(dep['amount_usd'])):.2f}\n"
            f"Status: {dep['status']}\n"
            f"Credited: {'yes' if dep['credited'] else 'no'}\n"
            f"Created: {dep['created_at']}\n"
            f"Updated: {dep['updated_at']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user['id']).pack())]]),
        )
        await callback.answer()
        return
    if callback_data.action.startswith('withdraws_'):
        page = max(int(callback_data.action.split('_')[1]), 1)
        page_size = 5
        offset = (page - 1) * page_size
        items = await fetchall(session, "SELECT * FROM withdraw_requests WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (user['id'], page_size, offset))
        total = await fetchone(session, "SELECT COUNT(*) AS c FROM withdraw_requests WHERE user_id=?", (user['id'],))
        total_pages = max((total['c'] + page_size - 1) // page_size, 1)
        await callback.message.answer(f"📤 Withdrawals for @{user['username'] or user['tg_id']}:", reply_markup=admin_user_withdraws_kb(user['id'], items, page, total_pages))
        await callback.answer()
        return
    if callback_data.action.startswith('withdraw_open_'):
        wdr_id = int(callback_data.action.split('_')[-1])
        wdr = await fetchone(session, 'SELECT * FROM withdraw_requests WHERE id=?', (wdr_id,))
        if not wdr:
            await callback.answer('Withdrawal not found.', show_alert=True)
            return
        await callback.message.answer(
            f"📤 Withdrawal #{wdr['id']}\n"
            f"Amount: ${Decimal(str(wdr['amount'])):.2f}\n"
            f"Fee: ${Decimal(str(wdr['fee_amount'])):.2f}\n"
            f"Net: ${Decimal(str(wdr['net_amount'])):.2f}\n"
            f"Status: {wdr['status']}\n"
            f"Requisites: {wdr['requisites']}\n"
            f"TX: {wdr['tx_info'] or '-'}\n"
            f"Created: {wdr['created_at']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Back to profile', callback_data=AdminUserCb(action='refresh', user_id=user['id']).pack())]]),
        )
        await callback.answer()
        return
    if callback_data.action == 'ban':
        await state.set_state(AdminBanReasonSG.reason)
        await state.update_data(ban_user_id=user['id'])
        await callback.message.answer(f"Enter ban reason for @{user['username'] or user['tg_id']}:")
        await callback.answer()
        return
    if callback_data.action == 'unban':
        await session.execute(
            'UPDATE users SET is_banned=0, ban_reason=NULL, banned_by=NULL, banned_at=NULL WHERE id=?',
            (user['id'],),
        )
        user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (callback_data.user_id,))
        await _send_admin_user_profile(callback, session, user)
        await callback.answer('User unbanned.')
        return
    if callback_data.action in {'add_balance', 'sub_balance'}:
        await state.set_state(AdminUserBalanceSG.amount)
        await state.update_data(user_id=user['id'], op=callback_data.action)
        await callback.message.answer(
            f"Enter amount in USD to {'add to' if callback_data.action == 'add_balance' else 'subtract from'} @{user['username'] or user['tg_id']}:"
        )
        await callback.answer()
        return
    await callback.answer('Unknown action.', show_alert=True)


@router.message(AdminUserBalanceSG.amount)
async def admin_user_balance_update(message: Message, state: FSMContext, session):
    data = await state.get_data()
    user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (data.get('user_id'),))
    if not user:
        await message.answer('User not found.')
        await state.clear()
        return
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer('Invalid amount. Enter positive number.')
        return

    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (user['id'],))
    if data.get('op') == 'add_balance':
        await session.execute(
            'UPDATE wallets SET available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
            (float(amount), user['id']),
        )
        await message.answer(f'Added ${amount:.2f} to @{user["username"] or user["tg_id"]}.')
        actor = message.from_user.username or message.from_user.id
        target = user['username'] or user['tg_id']
        for superadmin_id in set(get_settings().superadmin_ids):
            await safe_send(message.bot, superadmin_id, f"🛡 Admin @{actor} added ${amount:.2f} to @{target} (user_id={user['tg_id']}).")
    else:
        if Decimal(str(wallet['available_balance'])) < amount:
            await message.answer('Insufficient available balance for subtraction.')
            return
        await session.execute(
            'UPDATE wallets SET available_balance=available_balance-?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
            (float(amount), user['id']),
        )
        await message.answer(f'Subtracted ${amount:.2f} from @{user["username"] or user["tg_id"]}.')
        actor = message.from_user.username or message.from_user.id
        target = user['username'] or user['tg_id']
        for superadmin_id in set(get_settings().superadmin_ids):
            await safe_send(message.bot, superadmin_id, f"🛡 Admin @{actor} subtracted ${amount:.2f} from @{target} (user_id={user['tg_id']}).")

    updated = await fetchone(session, 'SELECT * FROM users WHERE id=?', (user['id'],))
    await _send_admin_user_profile(message, session, updated)
    await state.clear()


@router.message(AdminBanReasonSG.reason)
async def admin_ban_reason_save(message: Message, state: FSMContext, session):
    data = await state.get_data()
    user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (data.get('ban_user_id'),))
    if not user:
        await message.answer('User not found.')
        await state.clear()
        return
    reason = (message.text or '').strip()
    if not reason:
        await message.answer('Ban reason cannot be empty.')
        return
    banned_at = datetime.utcnow().isoformat()
    await session.execute(
        'UPDATE users SET is_banned=1, ban_reason=?, banned_by=?, banned_at=? WHERE id=?',
        (reason, message.from_user.id, banned_at, user['id']),
    )
    await message.answer(f"🚫 User @{user['username'] or user['tg_id']} banned.\nReason: {reason}")
    # auto-ban in monitored chat if configured
    row = await fetchone(session, "SELECT value FROM settings WHERE key='monitor_chat'")
    monitor_chat = row['value'] if row else ''
    if monitor_chat and str(user['tg_id']):
        try:
            chat_id = int(monitor_chat)
            await message.bot.ban_chat_member(chat_id=chat_id, user_id=user['tg_id'])
            await safe_send(
                message.bot,
                chat_id,
                f"🚫 User @{user['username'] or user['tg_id']} has been banned.\nReason: {reason}",
            )
        except Exception:
            pass
    await state.clear()


async def _withdraw_page(session, page: int, page_size: int = 5):
    offset = max(page - 1, 0) * page_size
    rows = await fetchall(
        session,
        "SELECT * FROM withdraw_requests ORDER BY id DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    total = await fetchone(session, "SELECT COUNT(*) AS c FROM withdraw_requests")
    total_pages = max((total['c'] + page_size - 1) // page_size, 1)
    return rows, total_pages


@router.message(F.text == '📤 Withdraw Requests')
async def admin_withdraw_list(message: Message, session):
    rows, total_pages = await _withdraw_page(session, page=1)
    if not rows:
        await message.answer('No pending withdraw requests.')
        return
    await message.answer('Withdrawal requests history (latest first):', reply_markup=admin_withdraws_list_kb(rows, 1, total_pages))


@router.callback_query(AdminWithdrawPageCb.filter())
async def admin_withdraw_page(callback: CallbackQuery, callback_data: AdminWithdrawPageCb, session):
    rows, total_pages = await _withdraw_page(session, page=callback_data.page)
    if not rows:
        await callback.answer('No requests on this page.', show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=admin_withdraws_list_kb(rows, callback_data.page, total_pages))
    await callback.answer()


@router.callback_query(AdminWithdrawCb.filter(F.action == 'open'))
async def admin_withdraw_open(callback: CallbackQuery, callback_data: AdminWithdrawCb, session):
    req = await withdrawals.get_withdraw(session, callback_data.withdraw_id)
    if not req:
        await callback.answer('Not found', show_alert=True)
        return
    user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (req['user_id'],))
    await callback.message.answer(
        f"Withdraw #{req['id']}\n"
        f"User: @{user['username'] or user['tg_id']}\n"
        f"Amount: ${Decimal(str(req['amount'])):.2f}\n"
        f"Fee: ${Decimal(str(req['fee_amount'])):.2f}\n"
        f"Net: ${Decimal(str(req['net_amount'])):.2f}\n"
        f"Requisites: {req['requisites']}",
        reply_markup=admin_withdraw_kb(req['id']) if req['status'] == 'PENDING' else None,
    )
    await callback.answer()


@router.callback_query(AdminWithdrawCb.filter(F.action == 'approve'))
async def admin_withdraw_approve_start(callback: CallbackQuery, callback_data: AdminWithdrawCb, state: FSMContext):
    await state.set_state(AdminWithdrawSG.tx_info)
    await state.update_data(withdraw_id=callback_data.withdraw_id)
    await callback.message.answer('Enter transaction hash or transaction link:')
    await callback.answer()


@router.message(AdminWithdrawSG.tx_info)
async def admin_withdraw_approve_finish(message: Message, state: FSMContext, session):
    data = await state.get_data()
    req = await withdrawals.get_withdraw(session, data['withdraw_id'])
    if not req:
        await message.answer('Withdraw request not found.')
        await state.clear()
        return

    tx = message.text.strip()
    ok = await withdrawals.approve_withdraw(session, message.from_user.id, req, tx)
    if not ok:
        await message.answer('Unable to approve this withdraw request.')
    else:
        await message.answer(f'Withdraw #{req["id"]} approved.')
        user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (req['user_id'],))
        if user:
            await safe_send(
                message.bot,
                user['tg_id'],
                f"✅ Withdrawal successfully processed.\n\nAmount: ${Decimal(str(req['amount'])):.2f}\nTransaction: {tx}",
            )
    await state.clear()


@router.callback_query(AdminWithdrawCb.filter(F.action == 'reject'))
async def admin_withdraw_reject(callback: CallbackQuery, callback_data: AdminWithdrawCb, session):
    req = await withdrawals.get_withdraw(session, callback_data.withdraw_id)
    if not req:
        await callback.answer('Not found', show_alert=True)
        return
    ok = await withdrawals.reject_withdraw(session, callback.from_user.id, req)
    if ok:
        user = await fetchone(session, 'SELECT * FROM users WHERE id=?', (req['user_id'],))
        if user:
            await safe_send(callback.bot, user['tg_id'], f'Your withdrawal #{req["id"]} was rejected.')
        await callback.message.answer(f'Withdraw #{req["id"]} rejected.')
    else:
        await callback.message.answer('Unable to reject this request.')
    await callback.answer()


async def _tx_page(session, page: int, page_size: int = 5):
    offset = max(page - 1, 0) * page_size
    rows = await fetchall(
        session,
        "SELECT d.*, u.username, u.tg_id FROM deposits d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    total = await fetchone(session, 'SELECT COUNT(*) AS c FROM deposits')
    total_pages = max((total['c'] + page_size - 1) // page_size, 1)
    return rows, total_pages


async def _deals_page(session, page: int, page_size: int = 5):
    offset = max(page - 1, 0) * page_size
    rows = await fetchall(session, "SELECT * FROM deals ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    total = await fetchone(session, 'SELECT COUNT(*) AS c FROM deals')
    total_pages = max((total['c'] + page_size - 1) // page_size, 1)
    return rows, total_pages


@router.message(F.text.in_({'📂 Deals', '🌐 All Deals'}))
async def admin_deals_list(message: Message, session):
    rows, total_pages = await _deals_page(session, 1)
    if not rows:
        await message.answer('No deals yet.')
        return
    await message.answer('Deals (latest first):', reply_markup=admin_deals_list_kb(rows, 1, total_pages))


@router.callback_query(AdminDealPageCb.filter())
async def admin_deals_page(callback: CallbackQuery, callback_data: AdminDealPageCb, session):
    rows, total_pages = await _deals_page(session, callback_data.page)
    if not rows:
        await callback.answer('No deals on this page.', show_alert=True)
        return
    await callback.message.edit_text('Deals (latest first):', reply_markup=admin_deals_list_kb(rows, callback_data.page, total_pages))
    await callback.answer()


@router.callback_query(AdminDealCb.filter())
async def admin_deals_open(callback: CallbackQuery, callback_data: AdminDealCb, session):
    deal = await fetchone(session, 'SELECT * FROM deals WHERE id=?', (callback_data.deal_id,))
    if not deal:
        await callback.answer('Deal not found.', show_alert=True)
        return
    buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
    seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
    msgs = await fetchall(session, 'SELECT * FROM deal_messages WHERE deal_id=? ORDER BY id ASC', (deal['id'],))
    history_lines = []
    for m in msgs:
        sender = buyer if m['sender_id'] == deal['buyer_id'] else seller
        sender_ref = f"@{sender['username'] or sender['tg_id']}" if sender else str(m['sender_id'])
        history_lines.append(f"{sender_ref}: {m['text'] or ''}")
    history = '\n'.join(history_lines) if history_lines else 'No messages yet.'
    await _send_deal_card_with_history(
        callback.message,
        deal,
        buyer,
        seller,
        history,
        len(msgs),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='⬅️ Back to deals', callback_data=AdminDealPageCb(page=1).pack())]
            ]
        ),
    )
    await callback.answer()


@router.message(F.text == '💳 Transactions')
async def admin_transactions(message: Message, session):
    rows, total_pages = await _tx_page(session, 1)
    if not rows:
        await message.answer('No transactions yet.')
        return
    await message.answer('Latest deposits:', reply_markup=admin_transactions_list_kb(rows, 1, total_pages))


@router.callback_query(AdminTxPageCb.filter())
async def admin_tx_page(callback: CallbackQuery, callback_data: AdminTxPageCb, session):
    rows, total_pages = await _tx_page(session, callback_data.page)
    if not rows:
        await callback.answer('No transactions on this page.', show_alert=True)
        return
    await callback.message.edit_text('Latest deposits:', reply_markup=admin_transactions_list_kb(rows, callback_data.page, total_pages))
    await callback.answer()


@router.callback_query(AdminTxCb.filter())
async def admin_tx_open(callback: CallbackQuery, callback_data: AdminTxCb, session):
    tx = await fetchone(
        session,
        'SELECT d.*, u.username, u.tg_id FROM deposits d JOIN users u ON u.id=d.user_id WHERE d.id=?',
        (callback_data.tx_id,),
    )
    if not tx:
        await callback.answer('Transaction not found.', show_alert=True)
        return
    await callback.message.answer(
        f"Deposit #{tx['id']}\n"
        f"User: @{tx['username'] or tx['tg_id']} ({tx['tg_id']})\n"
        f"Amount: ${Decimal(str(tx['amount_usd'])):.2f}\n"
        f"Status: {tx['status']}\n"
        f"Credited: {'yes' if tx['credited'] else 'no'}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='⬅️ Back to transactions', callback_data=AdminTxPageCb(page=1).pack())]
            ]
        ),
    )
    await callback.answer()


async def _disputes_page(session, page: int, mode: str = 'active', page_size: int = 5):
    offset = max(page - 1, 0) * page_size
    if mode == 'resolved':
        rows = await fetchall(
            session,
            "SELECT d.* FROM deals d JOIN disputes s ON s.deal_id=d.id WHERE s.status='RESOLVED' ORDER BY s.resolved_at DESC, d.id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        total = await fetchone(session, "SELECT COUNT(*) AS c FROM disputes WHERE status='RESOLVED'")
    else:
        rows = await fetchall(
            session,
            "SELECT * FROM deals WHERE status IN ('DISPUTE','DISPUTE_WAITING') ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )
        total = await fetchone(session, "SELECT COUNT(*) AS c FROM deals WHERE status IN ('DISPUTE','DISPUTE_WAITING')")
    total_pages = max((total['c'] + page_size - 1) // page_size, 1)
    return rows, total_pages


@router.message(F.text == '⚖️ Disputes')
async def admin_disputes_list(message: Message, session):
    rows, total_pages = await _disputes_page(session, 1, mode='active')
    if not rows:
        resolved_rows, resolved_pages = await _disputes_page(session, 1, mode='resolved')
        if not resolved_rows:
            await message.answer('No disputes right now.')
            return
        await message.answer('Resolved disputes history:', reply_markup=admin_disputes_list_kb(resolved_rows, 1, resolved_pages, mode='resolved'))
        return
    await message.answer('Disputes:', reply_markup=admin_disputes_list_kb(rows, 1, total_pages, mode='active'))


@router.callback_query(F.data.startswith('dsppg:'))
async def admin_disputes_page(callback: CallbackQuery, session):
    parts = callback.data.split(':')
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    mode = parts[2] if len(parts) > 2 and parts[2] in {'active', 'resolved'} else 'active'
    rows, total_pages = await _disputes_page(session, page, mode=mode)
    if not rows:
        await callback.answer('No disputes on this page.', show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=admin_disputes_list_kb(rows, page, total_pages, mode=mode))
    await callback.answer()


@router.callback_query(F.data == 'admin:disputes:active:1')
async def admin_disputes_back_active(callback: CallbackQuery, session):
    rows, total_pages = await _disputes_page(session, 1, mode='active')
    await callback.message.answer('Active disputes:', reply_markup=admin_disputes_list_kb(rows, 1, total_pages, mode='active'))
    await callback.answer()


@router.callback_query(AdminDisputeCb.filter(F.action.startswith('open_')))
async def admin_dispute_open(callback: CallbackQuery, callback_data: AdminDisputeCb, session):
    deal = await fetchone(session, 'SELECT * FROM deals WHERE id=?', (callback_data.deal_id,))
    dispute = await get_dispute_by_deal(session, callback_data.deal_id)
    if not deal or not dispute:
        await callback.answer('Dispute not found', show_alert=True)
        return
    buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
    seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
    opener = await fetchone(session, 'SELECT * FROM users WHERE id=?', (dispute['opened_by'],))
    buyer_ref = f"@{buyer['username']}" if buyer and buyer.get('username') else f"@{buyer['tg_id']}" if buyer else 'buyer'
    seller_ref = f"@{seller['username']}" if seller and seller.get('username') else f"@{seller['tg_id']}" if seller else 'seller'
    opener_ref = f"@{opener['username']}" if opener and opener.get('username') else f"@{opener['tg_id']}" if opener else 'N/A'
    resolver = await fetchone(session, 'SELECT * FROM users WHERE tg_id=?', (dispute['resolved_by'],)) if dispute.get('resolved_by') else None
    resolver_ref = f"@{resolver['username']}" if resolver and resolver.get('username') else f"@{dispute['resolved_by']}" if dispute.get('resolved_by') else '—'
    await callback.message.answer(
        f"⚖️ Resolving Dispute for Deal {deal['public_id']}\n"
        f"🆔 Deal DB ID: {deal['id']}\n"
        f"📝 Description: {deal['terms']}\n"
        f"💵 Amount: {Decimal(str(deal['amount'])):.2f} USDT\n"
        f"🛒 Buyer: {buyer_ref} (id={buyer['tg_id'] if buyer else '—'})\n"
        f"🏷 Seller: {seller_ref} (id={seller['tg_id'] if seller else '—'})\n"
        f"🚨 Dispute Opened By: {opener_ref} (id={opener['tg_id'] if opener else '—'})\n"
        f"🕒 Opened At: {dispute['created_at']}\n"
        f"✅ Closed By: {resolver_ref}\n"
        f"🧾 Dispute Status: {dispute['status']}\n"
        f"🧩 Resolution: {dispute['resolution_type'] or '—'}\n"
        f"📌 Reason: {dispute['reason_text']}\n\n"
        f"Select an action:",
        reply_markup=admin_dispute_kb(deal['id'], buyer_ref, seller_ref),
    )
    await callback.answer()


@router.callback_query(AdminDisputeCb.filter())
async def admin_dispute_actions(callback: CallbackQuery, callback_data: AdminDisputeCb, session, state: FSMContext):
    if callback_data.action.startswith('open_'):
        return
    deal = await fetchone(session, 'SELECT * FROM deals WHERE id=?', (callback_data.deal_id,))
    dispute = await get_dispute_by_deal(session, callback_data.deal_id)
    if not deal or not dispute:
        await callback.answer('Dispute not found', show_alert=True)
        return

    action = callback_data.action
    ok = False
    if action == 'buyer':
        ok = await resolve_buyer(session, callback.from_user.id, deal, dispute)
    elif action == 'seller':
        ok = await resolve_seller(session, callback.from_user.id, deal, dispute)
    elif action == 'split':
        ok = await resolve_split(session, callback.from_user.id, deal, dispute)
    elif action == 'resume':
        ok = await resume_deal(session, callback.from_user.id, deal, dispute)
    elif action == 'more':
        await state.update_data(deal_id=deal['id'])
        await callback.message.answer('Choose who should provide more info:', reply_markup=dispute_target_kb(deal['id']))
        await callback.answer()
        return
    if ok:
        buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
        seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
        admin_ref = f"@{callback.from_user.username or callback.from_user.id}"
        result_map = {
            'buyer': 'resolved in favor of Buyer',
            'seller': 'resolved in favor of Seller',
            'split': 'resolved with Split 50/50',
            'resume': 'cancelled and resumed',
        }
        result_text = result_map.get(action, 'updated')
        notify = f"⚖️ Dispute update for deal #{deal['public_id']}: {result_text}.\nBy admin: {admin_ref}"
        if buyer:
            await safe_send(callback.bot, buyer['tg_id'], notify)
        if seller:
            await safe_send(callback.bot, seller['tg_id'], notify)
    await callback.message.answer('Done.' if ok else 'Action failed.')
    await callback.answer()


@router.callback_query(AdminDisputeTargetCb.filter())
async def dispute_more_info_target_inline(callback: CallbackQuery, callback_data: AdminDisputeTargetCb, state: FSMContext):
    await state.update_data(deal_id=callback_data.deal_id, target=callback_data.target)
    await state.set_state(AdminDisputeMoreInfoSG.text)
    await callback.message.answer('Enter request text (users can respond with text/photos/files):')
    await callback.answer()


@router.message(AdminDisputeMoreInfoSG.text)
async def dispute_more_info_text(message: Message, state: FSMContext, session):
    data = await state.get_data()
    deal = await fetchone(session, 'SELECT * FROM deals WHERE id=?', (data['deal_id'],))
    dispute = await get_dispute_by_deal(session, data['deal_id'])
    ok = await request_more_info(session, message.from_user.id, deal, dispute, data['target'], message.text.strip())
    if ok:
        buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
        seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
        notif = f"Admin requested more info for deal #{deal['public_id']}:\n{message.text.strip()}\n\nYou can reply with text, photos, or files."
        if data['target'] in {'buyer', 'both'}:
            await safe_send(message.bot, buyer['tg_id'], notif)
        if data['target'] in {'seller', 'both'}:
            await safe_send(message.bot, seller['tg_id'], notif)
        await message.answer('More info requested.')
    else:
        await message.answer('Unable to request more info.')
    await state.clear()


@router.message(F.text == '⚙️ Settings')
async def admin_settings_show(message: Message, session):
    rows = await list_settings(session)
    if not rows:
        await message.answer('No settings configured yet.')
        return
    await message.answer(_render_settings_text(rows), reply_markup=settings_kb())


@router.callback_query(AdminSettingCb.filter())
async def admin_settings_select(callback: CallbackQuery, callback_data: AdminSettingCb, state: FSMContext):
    if callback_data.key == 'manage_admins':
        if not _is_superadmin(callback.from_user.id):
            await callback.answer('Only superadmin can manage admins.', show_alert=True)
            return
        await callback.message.answer("Admin management:", reply_markup=manage_admins_kb())
        await callback.answer()
        return
    await state.set_state(AdminSettingSG.value)
    await state.update_data(key=callback_data.key)
    if callback_data.key == 'monitor_chat':
        await callback.message.answer(
            "Enter monitor chat target.\n"
            "Supported formats:\n"
            "- chat id (e.g. -1001234567890)\n"
            "- @chat_username\n"
            "- chat title\n\n"
            "Send '-' to monitor all chats where bot is admin.\n"
            "Send '0' to disable moderation completely."
        )
    else:
        await callback.message.answer(f'Enter new value for {callback_data.key}:')
    await callback.answer()


@router.message(AdminSettingSG.value)
async def admin_settings_save(message: Message, state: FSMContext, session):
    data = await state.get_data()
    key = data['key']
    value = message.text.strip()
    if key == 'monitor_chat' and value == '-':
        value = ''
    if key in {'withdraw_fee_percent', 'withdraw_fee_amount', 'min_deal_amount', 'min_withdraw_amount'}:
        try:
            Decimal(value)
        except Exception:
            await message.answer('Invalid numeric value.')
            return
    await set_value(session, key, value)
    await message.answer(f'Setting {key} updated.')
    await state.clear()


@router.message(AdminManageAdminsSG.command)
async def manage_admins_command(message: Message, state: FSMContext, session):
    if not _is_superadmin(message.from_user.id):
        await message.answer('Only superadmin can manage admins.')
        await state.clear()
        return
    text = message.text.strip()
    target = await deals_service.find_user_by_username_or_id(session, text)
    if not target:
        await message.answer('User not found.')
        return
    await session.execute('INSERT OR IGNORE INTO admin_users(tg_id, granted_by) VALUES(?,?)', (target['tg_id'], message.from_user.id))
    await message.answer(f"✅ @{target['username'] or target['tg_id']} added as admin.", reply_markup=manage_admins_kb())
    await safe_send(message.bot, target['tg_id'], 'You have been granted admin access. Use 🛡 Admin Panel.', reply_markup=main_menu(is_admin=True))
    await state.clear()


@router.callback_query(AdminManageCb.filter())
async def manage_admins_callbacks(callback: CallbackQuery, callback_data: AdminManageCb, state: FSMContext, session):
    if not _is_superadmin(callback.from_user.id):
        await callback.answer('Only superadmin can manage admins.', show_alert=True)
        return
    if callback_data.action == 'menu':
        await callback.message.answer("Admin management:", reply_markup=manage_admins_kb())
        await callback.answer()
        return
    if callback_data.action == 'settings':
        rows = await list_settings(session)
        if not rows:
            await callback.message.answer('No settings configured yet.', reply_markup=settings_kb())
        else:
            await callback.message.answer(_render_settings_text(rows), reply_markup=settings_kb())
        await callback.answer()
        return
    if callback_data.action == 'add':
        await state.set_state(AdminManageAdminsSG.command)
        await callback.message.answer('Enter @username or tg_id to add admin:')
        await callback.answer()
        return
    if callback_data.action == 'remove':
        rows = await fetchall(session, "SELECT u.username, a.tg_id FROM admin_users a LEFT JOIN users u ON u.tg_id=a.tg_id ORDER BY a.created_at DESC")
        if not rows:
            await callback.message.answer('No admins to remove.', reply_markup=manage_admins_kb())
            await callback.answer()
            return
        await callback.message.answer('Select admin to remove:', reply_markup=manage_admins_remove_list_kb(rows))
        await callback.answer()
        return
    if callback_data.action == 'confirm_remove':
        await callback.message.answer(f"Are you sure to remove admin {callback_data.tg_id}?", reply_markup=manage_admin_confirm_kb(callback_data.tg_id))
        await callback.answer()
        return
    if callback_data.action == 'do_remove':
        await session.execute('DELETE FROM admin_users WHERE tg_id=?', (callback_data.tg_id,))
        rows = await fetchall(session, "SELECT u.username, a.tg_id FROM admin_users a LEFT JOIN users u ON u.tg_id=a.tg_id ORDER BY a.created_at DESC")
        if rows:
            await callback.message.answer('Admin removed. Remaining admins:', reply_markup=manage_admins_remove_list_kb(rows))
        else:
            await callback.message.answer('Admin removed. No admins left.', reply_markup=manage_admins_kb())
        await callback.answer()


@router.message(F.text == '📢 Broadcast')
async def admin_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(BroadcastSG.text)
    await message.answer('Send broadcast text. Formatting from Telegram will be preserved.')


async def _broadcast_send_to_all(bot, session, text_html: str, photo_file_id: str | None = None) -> int:
    users = await fetchall(session, 'SELECT tg_id FROM users')
    for user in users:
        if photo_file_id:
            await safe_send_photo(bot, user['tg_id'], photo_file_id, caption=text_html, parse_mode='HTML')
        else:
            await safe_send(bot, user['tg_id'], text_html, parse_mode='HTML')
    return len(users)


@router.message(BroadcastSG.text)
async def admin_broadcast_collect_text(message: Message, state: FSMContext):
    text_html = (message.html_text or '').strip()
    if not text_html:
        await message.answer('Broadcast text cannot be empty. Send text message.')
        return
    await state.update_data(text_html=text_html)
    await state.set_state(BroadcastSG.photo)
    await message.answer('Now send a photo for the broadcast, or use the button below.', reply_markup=broadcast_skip_photo_kb())


@router.message(BroadcastSG.photo, F.photo)
async def admin_broadcast_with_photo(message: Message, state: FSMContext, session):
    data = await state.get_data()
    text_html = data.get('text_html')
    if not text_html:
        await message.answer('Broadcast text not found. Start again.')
        await state.clear()
        return
    photo_file_id = message.photo[-1].file_id
    sent = await _broadcast_send_to_all(message.bot, session, text_html=text_html, photo_file_id=photo_file_id)
    await message.answer(f'Broadcast sent to {sent} users.')
    await state.clear()


@router.callback_query(BroadcastCb.filter(F.action == 'skip_photo'), BroadcastSG.photo)
async def admin_broadcast_without_photo(callback: CallbackQuery, state: FSMContext, session):
    data = await state.get_data()
    text_html = data.get('text_html')
    if not text_html:
        await callback.message.answer('Broadcast text not found. Start again.')
        await state.clear()
        await callback.answer()
        return
    sent = await _broadcast_send_to_all(callback.bot, session, text_html=text_html)
    await callback.message.answer(f'Broadcast sent to {sent} users.')
    await state.clear()
    await callback.answer()


@router.message(BroadcastSG.photo)
async def admin_broadcast_photo_invalid(message: Message):
    await message.answer('Send a photo or press "➡️ Send without photo".', reply_markup=broadcast_skip_photo_kb())
