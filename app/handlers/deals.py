from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.callbacks import CreateDealRoleCb, DealActionCb, DealPageCb, DealRateCb
from app.config import get_settings
from app.db.repo import fetchall, fetchone, get_user_by_tg_id
from app.keyboards.inline import (
    active_deal_kb,
    cancel_confirm_kb,
    complete_confirm_kb,
    create_deal_preview_kb,
    deals_list_kb,
    offer_sent_kb,
    pending_deal_kb,
    rating_kb,
    reply_msg_kb,
    seller_response_kb,
)
from app.services import deals as deal_service
from app.services.disputes import open_dispute
from app.services.notifications import safe_send
from app.services.settings import get_decimal, get_value
from app.states import CreateDealSG, DealChatSG, OpenDisputeSG

router = Router()
MENU_BUTTONS = {'💼 My Deals', '➕ Create Deal', '👤 Profile', '💰 Balance', '📤 Withdraw', '📥 Deposit', '🛠 Support', '🏪 Shop'}


def render_deal_card(deal: dict, buyer: dict, seller: dict) -> str:
    return (
        f"🔥 Deal: #{deal['public_id']}\n\n"
        f"Seller: @{seller['username'] or seller['tg_id']}\n"
        f"Buyer: @{buyer['username'] or buyer['tg_id']}\n\n"
        f"Amount: {Decimal(str(deal['amount'])):.2f}$\n"
        f"Terms: {deal['terms']}\n\n"
        f"📸 Document important events with videos or photos. They will help you in case of a dispute."
    )


def render_complete_prompt(deal: dict, buyer: dict, seller: dict) -> str:
    return (
        f"📫 A request has been received to ✅ complete the deal\n"
        f"Number: #{deal['public_id']}\n\n"
        f"Seller: @{seller['username'] or seller['tg_id']}\n"
        f"Buyer: @{buyer['username'] or buyer['tg_id']}\n\n"
        f"Amount: {Decimal(str(deal['amount'])):.2f}$\n"
        f"Terms: {deal['terms']}\n\n"
        f"⚠️ Make sure the deal was successful. After confirmation, it will not be possible to start a dispute."
    )


@router.callback_query(F.data == 'noop')
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.message(StateFilter(CreateDealSG.seller, CreateDealSG.amount, CreateDealSG.terms), F.text.in_(MENU_BUTTONS))
async def interrupt_create_deal_by_menu(message: Message, state: FSMContext, session):
    await state.clear()
    if message.text == '🛠 Support':
        cfg = get_settings()
        username = await get_value(session, 'support_admin_username', cfg.support_admin_username)
        clean = username.strip()
        if not clean.startswith('@'):
            clean = f'@{clean}'
        await message.answer(f'Support: {clean}')
        return
    await message.answer('Previous deal creation was cancelled.')


@router.message(F.text == '💼 My Deals')
async def my_deals(message: Message, session, state: FSMContext):
    await state.clear()
    user = await get_user_by_tg_id(session, message.from_user.id)
    if not user:
        await message.answer('Please use /start first.')
        return
    deals, total_pages = await deal_service.get_user_deals_page(session, user['id'], page=1, page_size=5)
    if not deals:
        await message.answer('No deals yet.')
        return
    await message.answer('Your deals:', reply_markup=deals_list_kb(deals, 1, total_pages))


@router.callback_query(DealPageCb.filter())
async def my_deals_page(callback: CallbackQuery, callback_data: DealPageCb, session):
    user = await get_user_by_tg_id(session, callback.from_user.id)
    deals, total_pages = await deal_service.get_user_deals_page(session, user['id'], page=callback_data.page, page_size=5)
    if not deals:
        await callback.answer('No deals on this page.', show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=deals_list_kb(deals, callback_data.page, total_pages))
    await callback.answer()


@router.message(F.text == '➕ Create Deal')
async def deal_create_start(message: Message, state: FSMContext):
    await state.set_state(CreateDealSG.seller)
    await message.answer('🆕 New a deal\n\n⬇️ Enter @username or User ID:')


@router.message(CreateDealSG.seller)
async def deal_create_seller(message: Message, state: FSMContext, session):
    raw_counterparty = message.text.strip()
    normalized_input = raw_counterparty[1:] if raw_counterparty.startswith('@') else raw_counterparty
    my_username = (message.from_user.username or '').strip().lower()
    if my_username and normalized_input.lower() == my_username:
        await message.answer('You cannot create deal with yourself.')
        return
    if normalized_input.isdigit() and int(normalized_input) == message.from_user.id:
        await message.answer('You cannot create deal with yourself.')
        return

    seller = await deal_service.find_user_by_username_or_id(session, raw_counterparty)
    me = await get_user_by_tg_id(session, message.from_user.id)
    if not seller:
        await message.answer('User not found. Enter valid @username or User ID:')
        return
    if seller['id'] == me['id']:
        await message.answer('You cannot create deal with yourself.')
        return

    await state.update_data(counterparty_id=seller['id'])
    username = f"@{seller['username']}" if seller.get('username') else 'N/A'
    completed = await fetchone(
        session,
        "SELECT COUNT(*) AS c FROM deals WHERE status='COMPLETED' AND (buyer_id=? OR seller_id=?)",
        (seller['id'], seller['id']),
    )
    disputes_lost = await fetchone(
        session,
        "SELECT COUNT(*) AS c FROM disputes d JOIN deals x ON x.id=d.deal_id WHERE d.status='RESOLVED' AND ((d.resolution_type='BUYER' AND x.seller_id=?) OR (d.resolution_type='SELLER' AND x.buyer_id=?))",
        (seller['id'], seller['id']),
    )
    purchases = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE buyer_id=? AND status='COMPLETED'", (seller['id'],))
    sales = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE seller_id=? AND status='COMPLETED'", (seller['id'],))
    reviews = await fetchone(session, 'SELECT COUNT(*) AS c, COALESCE(AVG(stars),0) AS avg FROM reviews WHERE to_user_id=?', (seller['id'],))
    await message.answer(
        f"🧽 User: {username}\n🪪 ID: {seller['tg_id']}\n\n"
        f"🤝 Successful transactions: {completed['c']}\n⚖ Disputes lost: {disputes_lost['c']}\n\n"
        f"📈 Total purchase amount: {Decimal(str(purchases['s'])):.2f}$\n📉 Total sale amount: {Decimal(str(sales['s'])):.2f}$\n\n"
        f"🗂️ Rating: {reviews['c']} reviews | {Decimal(str(reviews['avg'])):.1f} ⭐",
        reply_markup=create_deal_preview_kb(),
    )
    await state.set_state(CreateDealSG.amount)


@router.callback_query(CreateDealRoleCb.filter(F.action == 'start'))
async def deal_preview_start(callback: CallbackQuery, session):
    user = await get_user_by_tg_id(session, callback.from_user.id)
    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (user['id'],)) if user else None
    if not wallet or Decimal(str(wallet['available_balance'])) <= 0:
        await callback.answer('Please top up your balance before creating a deal.', show_alert=True)
        return
    await callback.message.answer('⬇ Enter the amount in $ for creating a purchase deal:')
    await callback.answer()


@router.callback_query(CreateDealRoleCb.filter(F.action == 'hide'))
async def deal_preview_hide(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Hidden.')
    await callback.answer()


@router.message(CreateDealSG.amount)
async def deal_create_amount(message: Message, state: FSMContext, session):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer('Invalid amount. Try again.')
        return
    min_deal = await get_decimal(session, 'min_deal_amount', Decimal(str(get_settings().min_deal_amount)))
    if amount < min_deal:
        await message.answer('Amount is below minimum.')
        await state.clear()
        return
    me = await get_user_by_tg_id(session, message.from_user.id)
    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (me['id'],)) if me else None
    if not wallet or Decimal(str(wallet['available_balance'])) < amount:
        await message.answer('Insufficient balance for this deal amount.')
        await state.clear()
        return
    await state.update_data(amount=str(amount))
    await state.set_state(CreateDealSG.terms)
    await message.answer('⬇️ Enter the terms of this deal:')


@router.message(CreateDealSG.terms)
async def deal_create_terms(message: Message, state: FSMContext, session):
    data = await state.get_data()
    me = await get_user_by_tg_id(session, message.from_user.id)
    other = await fetchone(session, 'SELECT * FROM users WHERE id=?', (data['counterparty_id'],))

    buyer_id, seller_id = me['id'], other['id']

    deal = await deal_service.create_deal(session, buyer_id=buyer_id, seller_id=seller_id, amount=Decimal(data['amount']), terms=message.text.strip())
    if not deal:
        await message.answer('Amount is below minimum.')
        await state.clear()
        return

    seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (seller_id,))
    await message.answer(
        f"✅ Offer sent\nNumber: #{deal['public_id']}\n\nUser: @{other['username'] or other['tg_id']}\n\nWait for the 🤖 bot notification",
        reply_markup=offer_sent_kb(deal['id']),
    )

    buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (buyer_id,))
    await safe_send(
        message.bot,
        other['tg_id'],
        (
            f"New offer #{deal['public_id']}\n"
            f"Buyer: @{buyer['username'] or buyer['tg_id']}\n"
            f"Seller: @{seller['username'] or seller['tg_id']}\n"
            f"Amount: {Decimal(str(deal['amount'])):.2f}$\n"
            f"Terms: {deal['terms']}"
        ),
        reply_markup=seller_response_kb(deal['id']),
    )
    await state.clear()


@router.callback_query(DealActionCb.filter(F.action == 'open'))
async def open_deal_card(callback: CallbackQuery, callback_data: DealActionCb, session):
    deal = await deal_service.get_deal(session, callback_data.deal_id)
    if not deal:
        await callback.answer('Deal not found', show_alert=True)
        return
    buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
    seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
    kb = active_deal_kb(deal['id']) if deal['status'] == 'ACTIVE' else pending_deal_kb(deal['id']) if deal['status'] == 'PENDING' else None
    await callback.message.answer(render_deal_card(deal, buyer, seller), reply_markup=kb)
    await callback.answer()


@router.callback_query(DealRateCb.filter())
async def rate_deal(callback: CallbackQuery, callback_data: DealRateCb, session):
    deal = await deal_service.get_deal(session, callback_data.deal_id)
    if not deal or deal['status'] != 'COMPLETED':
        await callback.answer('Rating unavailable.', show_alert=True)
        return
    from_user = await get_user_by_tg_id(session, callback.from_user.id)
    to_user_id = deal['seller_id'] if from_user['id'] == deal['buyer_id'] else deal['buyer_id']
    ok = await deal_service.leave_review(session, deal['id'], from_user['id'], to_user_id, callback_data.stars)
    if ok:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer('Thanks for your review!' if ok else 'You already rated this deal.', show_alert=True)


@router.callback_query(DealActionCb.filter())
async def deal_actions(callback: CallbackQuery, callback_data: DealActionCb, session, state: FSMContext):
    deal = await deal_service.get_deal(session, callback_data.deal_id)
    if not deal:
        await callback.answer('Deal not found', show_alert=True)
        return

    if callback_data.action == 'offer_cancel':
        if deal['status'] != 'PENDING':
            await callback.answer('Offer is no longer active.', show_alert=True)
            return
        await session.execute("UPDATE deals SET status='CANCELLED', updated_at=CURRENT_TIMESTAMP WHERE id=?", (deal['id'],))
        seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
        await callback.message.edit_text('Offer cancelled.')
        if seller:
            await safe_send(
                callback.bot,
                seller['tg_id'],
                f"❌ Offer #{deal['public_id']} was cancelled by buyer before acceptance.",
            )
        await callback.answer()
        return

    if callback_data.action == 'cancel_pending':
        if deal['status'] != 'PENDING':
            await callback.answer('Action unavailable.', show_alert=True)
            return
        # cancel pending by either party, funds return to buyer
        await session.execute("UPDATE deals SET status='CANCELLED', updated_at=CURRENT_TIMESTAMP WHERE id=?", (deal['id'],))
        buyer_w = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (deal['buyer_id'],))
        if buyer_w and Decimal(str(buyer_w['frozen_balance'])) >= Decimal(str(deal['amount'])):
            await session.execute('UPDATE wallets SET frozen_balance=frozen_balance-?, available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?', (deal['amount'], deal['amount'], deal['buyer_id']))
        await callback.message.answer('Pending deal cancelled and funds returned.')
        await callback.answer()
        return

    buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
    seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))

    if callback_data.action in {'sendmsg', 'complete', 'cancel', 'dispute'} and deal['status'] != 'ACTIVE':
        await callback.answer('This action is no longer available for current deal status.', show_alert=True)
        return

    action = callback_data.action
    if action == 'accept':
        ok = await deal_service.accept_deal(session, callback.from_user.id, deal)
        if ok:
            info = render_deal_card(deal, buyer, seller)
            await safe_send(callback.bot, buyer['tg_id'], info, reply_markup=active_deal_kb(deal['id']))
            await safe_send(callback.bot, seller['tg_id'], info, reply_markup=active_deal_kb(deal['id']))
            await callback.message.edit_text(f'Deal #{deal["public_id"]} accepted.')
        else:
            await callback.answer('Action unavailable.', show_alert=True)
            return
    elif action == 'decline':
        ok = await deal_service.decline_deal(session, callback.from_user.id, deal)
        if ok:
            await callback.message.edit_text(f'Deal #{deal["public_id"]} declined.')
            await safe_send(
                callback.bot,
                buyer['tg_id'],
                f"❌ Your offer #{deal['public_id']} was declined by seller.",
            )
        else:
            await callback.answer('Action unavailable.', show_alert=True)
            return
    elif action == 'complete':
        await callback.message.answer(render_complete_prompt(deal, buyer, seller), reply_markup=complete_confirm_kb(deal['id']))
    elif action == 'complete_confirm':
        started = await deal_service.start_complete_request(session, callback.from_user.id, deal)
        if not started:
            await callback.answer('Action unavailable.', show_alert=True)
            return
        ok, completed_now = await deal_service.confirm_complete_request(session, callback.from_user.id, deal)
        if not ok:
            await callback.answer('Action unavailable.', show_alert=True)
            return
        if completed_now:
            done_text = (
                f"✅ Deal #{deal['public_id']} successfully completed\n\n"
                f"Seller: @{seller['username'] or seller['tg_id']}\n"
                f"Buyer: @{buyer['username'] or buyer['tg_id']}\n\n"
                f"⭐️ Don't forget to leave a review for @{seller['username'] or seller['tg_id']}"
            )
            await safe_send(callback.bot, buyer['tg_id'], done_text, reply_markup=rating_kb(deal['id']))
            await safe_send(callback.bot, seller['tg_id'], done_text, reply_markup=rating_kb(deal['id']))
        else:
            other = seller if callback.from_user.id == buyer['tg_id'] else buyer
            await callback.message.answer(
                f"✅ Confirmation message for deal #{deal['public_id']} sent!\n\n🕰 Waiting for confirmation from @{other['username'] or other['tg_id']}"
            )
            await safe_send(callback.bot, other['tg_id'], render_complete_prompt(deal, buyer, seller), reply_markup=active_deal_kb(deal['id']))
    elif action == 'cancel':
        started = await deal_service.start_cancel_request(session, callback.from_user.id, deal)
        if not started:
            await callback.answer('Action unavailable.', show_alert=True)
            return
        await callback.message.answer(
            f"❌ Cancel request for deal #{deal['public_id']} sent.\nBoth sides must confirm.",
            reply_markup=cancel_confirm_kb(deal['id']),
        )
        other = seller if callback.from_user.id == buyer['tg_id'] else buyer
        await safe_send(
            callback.bot,
            other['tg_id'],
            f"⚠️ {callback.from_user.username or callback.from_user.id} requested to cancel deal #{deal['public_id']}.\nPlease confirm cancellation.",
            reply_markup=cancel_confirm_kb(deal['id']),
        )
    elif action == 'cancel_confirm':
        ok, cancelled_now = await deal_service.confirm_cancel_request(session, callback.from_user.id, deal)
        if not ok:
            await callback.answer('Action unavailable.', show_alert=True)
            return
        if cancelled_now:
            notify = f"❌ Deal #{deal['public_id']} cancelled by mutual confirmation.\nFunds returned to buyer."
            await safe_send(callback.bot, buyer['tg_id'], notify)
            await safe_send(callback.bot, seller['tg_id'], notify)
            await callback.message.answer('Deal cancelled and funds returned to buyer.')
        else:
            other = seller if callback.from_user.id == buyer['tg_id'] else buyer
            await callback.message.answer(f"✅ Your cancel confirmation for deal #{deal['public_id']} received.\nWaiting for @{other['username'] or other['tg_id']}.")
    elif action == 'sendmsg':
        recipient = seller if callback.from_user.id == buyer['tg_id'] else buyer
        await state.set_state(DealChatSG.message)
        await state.update_data(deal_id=deal['id'], recipient_id=recipient['id'])
        await callback.message.answer(f"🕊️ Enter a message for user @{recipient['username'] or recipient['tg_id']}")
    elif action == 'dispute':
        await state.set_state(OpenDisputeSG.reason)
        await state.update_data(deal_id=deal['id'])
        await callback.message.answer('Enter dispute reason and optional attachment.')
    await callback.answer()


@router.message(DealChatSG.message)
async def deal_chat_send(message: Message, state: FSMContext, session):
    data = await state.get_data()
    deal = await deal_service.get_deal(session, data['deal_id'])
    if deal['status'] != 'ACTIVE':
        await message.answer('This deal is not active anymore.')
        await state.clear()
        return
    sender = await get_user_by_tg_id(session, message.from_user.id)
    recipient = await fetchone(session, 'SELECT * FROM users WHERE id=?', (data['recipient_id'],))
    await deal_service.save_deal_message(session, deal['id'], sender['id'], recipient['id'], message.text)
    await message.answer('✅ Message sent')
    await safe_send(
        message.bot,
        recipient['tg_id'],
        f"✉️ Message from @{sender['username'] or sender['tg_id']}\nDeal: #{deal['public_id']}\n\n{message.text}",
        reply_markup=reply_msg_kb(deal['id']),
    )
    await state.clear()


@router.message(OpenDisputeSG.reason)
async def dispute_reason(message: Message, state: FSMContext, session):
    data = await state.get_data()
    deal = await deal_service.get_deal(session, data['deal_id'])
    attachments = None
    if message.photo:
        attachments = {'type': 'photo', 'file_id': message.photo[-1].file_id}
    elif message.document:
        attachments = {'type': 'document', 'file_id': message.document.file_id}

    dispute = await open_dispute(session, message.from_user.id, deal, message.text or 'No text', attachments)
    if not dispute:
        await message.answer('Unable to open dispute.')
    else:
        await message.answer('Dispute opened.')
        buyer = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['buyer_id'],))
        seller = await fetchone(session, 'SELECT * FROM users WHERE id=?', (deal['seller_id'],))
        opener_ref = f"@{message.from_user.username or message.from_user.id}"
        if buyer and buyer['tg_id'] != message.from_user.id:
            await safe_send(
                message.bot,
                buyer['tg_id'],
                f"⚖️ Dispute opened for deal #{deal['public_id']} by {opener_ref}.\nReason: {message.text or 'No text'}",
            )
        if seller and seller['tg_id'] != message.from_user.id:
            await safe_send(
                message.bot,
                seller['tg_id'],
                f"⚖️ Dispute opened for deal #{deal['public_id']} by {opener_ref}.\nReason: {message.text or 'No text'}",
            )
        cfg = get_settings()
        admin_rows = await fetchall(session, 'SELECT tg_id FROM admin_users')
        admin_ids = {x['tg_id'] for x in admin_rows}
        for admin_tg_id in set(cfg.superadmin_ids) | admin_ids:
            await safe_send(message.bot, admin_tg_id, f"Dispute opened for deal #{deal['public_id']}")
    await state.clear()
