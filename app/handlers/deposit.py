from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.callbacks import DepositCb
from app.db.repo import get_user_by_tg_id
from app.keyboards.inline import deposit_invoice_kb
from app.services.deposits import cancel_deposit, check_and_credit_deposit, create_deposit_invoice, set_deposit_notify_message
from app.states import DepositSG

router = Router()
MENU_BUTTONS = {
    '💼 My Deals', '➕ Create Deal', '👤 Profile', '💰 Balance', '📤 Withdraw', '📥 Deposit', '🛠 Support', '🏪 Shop',
    '🛡 Admin Panel', '🔎 Find User', '📊 Users', '📂 Deals', '🌐 All Deals', '💳 Transactions', '📤 Withdraw Requests',
    '⚖️ Disputes', '📢 Broadcast', '⚙️ Settings', '⬅️ User Menu',
}


def _parse_amount(text: str) -> Decimal:
    cleaned = (text or '').strip().replace(' ', '').replace('$', '').replace(',', '.')
    return Decimal(cleaned)


@router.message(StateFilter(DepositSG.amount), F.text.in_(MENU_BUTTONS))
async def interrupt_deposit_by_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer('Deposit flow cancelled. Menu action received.')


@router.message(F.text == '📥 Deposit')
async def deposit_start(message: Message, state: FSMContext):
    await state.set_state(DepositSG.amount)
    await message.answer('💳 Deposit via CryptoBot\n\nEnter amount in USD (min 1$):')


@router.message(DepositSG.amount)
async def deposit_amount(message: Message, state: FSMContext, session):
    try:
        amount = _parse_amount(message.text)
        if amount < Decimal('1'):
            raise ValueError
    except Exception:
        await message.answer('Invalid amount. Enter number, e.g. 5 or 10.50')
        return

    user = await get_user_by_tg_id(session, message.from_user.id)
    try:
        dep = await create_deposit_invoice(session, user['id'], amount)
    except Exception as e:
        err = str(e)
        if 'non-JSON response' in err:
            await message.answer('Unable to create invoice right now (CryptoBot temporary error). Please try again in 1-2 minutes.')
        else:
            await message.answer(f'Unable to create invoice: {err}')
        await state.clear()
        return

    sent = await message.answer(
        f"Invoice created for ${Decimal(str(dep['amount_usd'])):.2f}.\n"
        f"After payment, press ✅ I have paid.",
        reply_markup=deposit_invoice_kb(dep['id'], dep['pay_url']),
    )
    await set_deposit_notify_message(session, dep['id'], message.chat.id, sent.message_id)
    await state.clear()


@router.callback_query(DepositCb.filter(F.action == 'cancel'))
async def deposit_cancel(callback: CallbackQuery, callback_data: DepositCb, session):
    user = await get_user_by_tg_id(session, callback.from_user.id)
    ok = await cancel_deposit(session, callback_data.deposit_id, user['id'])
    if ok:
        await callback.message.edit_text('Deposit request cancelled.')
    else:
        await callback.answer('Unable to cancel this deposit request.', show_alert=True)
        return
    await callback.answer()


@router.callback_query(DepositCb.filter(F.action == 'check'))
async def deposit_check(callback: CallbackQuery, callback_data: DepositCb, session):
    user = await get_user_by_tg_id(session, callback.from_user.id)
    try:
        ok, text = await check_and_credit_deposit(session, callback_data.deposit_id, user['id'])
    except Exception as e:
        await callback.answer(f'Check failed: {e}', show_alert=True)
        return

    if ok:
        await callback.message.answer(f'✅ {text}')
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer(text, show_alert=True)
    await callback.answer()
