from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.callbacks import WithdrawMethodCb
from app.config import get_settings
from app.db.repo import fetchall, fetchone, get_user_by_tg_id
from app.keyboards.inline import admin_withdraw_kb, withdraw_cancel_kb, withdraw_method_kb
from app.services.notifications import safe_send
from app.services.settings import get_decimal
from app.services.withdrawals import create_withdraw_request
from app.states import WithdrawSG

router = Router()
MENU_BUTTONS = {
    '💼 My Deals', '➕ Create Deal', '👤 Profile', '💰 Balance', '📤 Withdraw', '📥 Deposit', '🛠 Support', '🏪 Shop',
    '🛡 Admin Panel', '🔎 Find User', '📊 Users', '📂 Deals', '🌐 All Deals', '💳 Transactions', '📤 Withdraw Requests',
    '⚖️ Disputes', '📢 Broadcast', '⚙️ Settings', '⬅️ User Menu',
}


@router.message(StateFilter(WithdrawSG.amount, WithdrawSG.method, WithdrawSG.requisites), F.text.in_(MENU_BUTTONS))
async def interrupt_withdraw_by_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('Withdrawal flow cancelled. Menu action received.')


@router.message(F.text == '📤 Withdraw')
async def withdraw_start(message: Message, state: FSMContext, session):
    user = await get_user_by_tg_id(session, message.from_user.id)
    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (user['id'],)) if user else None
    min_amount = await get_decimal(session, 'min_withdraw_amount', Decimal('4.50'))
    fee_percent = await get_decimal(session, 'withdraw_fee_percent', Decimal('0'))
    fee_fixed = await get_decimal(session, 'withdraw_fee_amount', Decimal('0.50'))

    if not wallet or Decimal(str(wallet['available_balance'])) < min_amount:
        await message.answer(f'💰 Withdrawal\n\n🌇 Withdrawal is possible only from {min_amount:.2f}$')
        return

    await message.answer(
        f"💰 Withdrawal\n\n"
        f"🫰 Current balance: {Decimal(str(wallet['available_balance'])):.2f}$\n\n"
        f"Enter the amount in $ for withdrawal\n"
        f"Example: 10, 20, 30\n\n"
        f"💸 Fee: {fee_percent:.2f}% + fixed ${fee_fixed:.2f}\n"
        f"🔥 Minimum withdrawal: {min_amount:.2f}$"
    )
    await state.set_state(WithdrawSG.amount)


@router.message(WithdrawSG.amount)
async def withdraw_amount(message: Message, state: FSMContext, session):
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer('Invalid amount, try again.')
        return

    min_amount = await get_decimal(session, 'min_withdraw_amount', Decimal('4.50'))
    fee_percent = await get_decimal(session, 'withdraw_fee_percent', Decimal('0'))
    fee_fixed = await get_decimal(session, 'withdraw_fee_amount', Decimal('0.50'))
    if amount < min_amount:
        await message.answer(f'Minimum withdrawal is {min_amount:.2f}$')
        return

    percent_fee = (amount * fee_percent / Decimal('100')).quantize(Decimal('0.01'))
    fee_amount = (fee_fixed + percent_fee).quantize(Decimal('0.01'))
    net = amount - fee_amount
    if net <= 0:
        await message.answer('Amount is too small after service fee.')
        return

    await state.update_data(amount=str(amount), net=str(net))
    await message.answer(
        f"⚠️ Service fee: {fee_amount:.2f}$ ({fee_percent:.2f}% + fixed ${fee_fixed:.2f})\n\n"
        f"⬇️ Select the withdrawal method for {net:.2f}$",
        reply_markup=withdraw_method_kb(),
    )
    await state.set_state(WithdrawSG.method)


@router.callback_query(F.data == 'withdraw:cancel')
async def withdraw_cancel(callback: CallbackQuery, state: FSMContext, session):
    await state.clear()
    user = await get_user_by_tg_id(session, callback.from_user.id)
    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (user['id'],)) if user else None
    if wallet:
        await callback.message.answer(
            f"Withdrawal cancelled.\n\n💰 Balance\nAvailable: {Decimal(str(wallet['available_balance'])):.2f}$\nFrozen: {Decimal(str(wallet['frozen_balance'])):.2f}$"
        )
    else:
        await callback.message.answer('Withdrawal cancelled.')
    await callback.answer()


@router.callback_query(WithdrawMethodCb.filter())
async def withdraw_method(callback: CallbackQuery, callback_data: WithdrawMethodCb, state: FSMContext):
    await state.update_data(method=callback_data.method)
    await state.set_state(WithdrawSG.requisites)
    await callback.message.answer(
        f'💼 Please enter your USDT {callback_data.method} wallet address for withdrawal:\n\n',
        reply_markup=withdraw_cancel_kb(),
    )
    await callback.answer()


@router.message(WithdrawSG.requisites)
async def withdraw_requisites(message: Message, state: FSMContext, session):
    data = await state.get_data()
    user = await get_user_by_tg_id(session, message.from_user.id)
    requisites = f"{data['method']}: {message.text.strip()}"

    req = await create_withdraw_request(session, user['id'], Decimal(data['amount']), requisites)
    if not req:
        await message.answer('Unable to create request. Check balance/minimum amount.')
        await state.clear()
        return

    await message.answer(
        f"✅ Withdrawal request created\n"
        f"ID: {req['id']}\n"
        f"Amount: {Decimal(str(req['amount'])):.2f}$\n"
        f"Service fee: {Decimal(str(req['fee_amount'])):.2f}$\n"
        f"To receive: {Decimal(str(req['net_amount'])):.2f}$"
    )

    cfg = get_settings()
    admin_rows = await fetchall(session, 'SELECT tg_id FROM admin_users')
    admin_ids = {x['tg_id'] for x in admin_rows}
    for admin_tg_id in set(cfg.superadmin_ids) | admin_ids:
        await safe_send(
            message.bot,
            admin_tg_id,
            (
                f"📤 New withdraw request #{req['id']}\n"
                f"User: @{message.from_user.username or message.from_user.id}\n"
                f"Amount: {Decimal(str(req['amount'])):.2f}$\n"
                f"Fee: {Decimal(str(req['fee_amount'])):.2f}$\n"
                f"Net: {Decimal(str(req['net_amount'])):.2f}$\n"
                f"Requisites: {requisites}"
            ),
            reply_markup=admin_withdraw_kb(req['id']),
        )

    await state.clear()
