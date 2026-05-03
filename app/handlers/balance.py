from decimal import Decimal

from aiogram import F, Router
from aiogram.types import Message
from app.db.repo import fetchone, get_user_by_tg_id

router = Router()


@router.message(F.text.in_({'👤 Profile', '💰 Balance'}))
async def show_balance(message: Message, session):
    user = await get_user_by_tg_id(session, message.from_user.id)
    if not user:
        await message.answer('Please use /start first.')
        return

    wallet = await fetchone(session, 'SELECT * FROM wallets WHERE user_id=?', (user['id'],))

    completed = await fetchone(
        session,
        "SELECT COUNT(*) AS c FROM deals WHERE status='COMPLETED' AND (buyer_id=? OR seller_id=?)",
        (user['id'], user['id']),
    )
    disputes_lost = await fetchone(
        session,
        "SELECT COUNT(*) AS c FROM disputes d JOIN deals x ON x.id=d.deal_id WHERE d.status='RESOLVED' AND ((d.resolution_type='BUYER' AND x.seller_id=?) OR (d.resolution_type='SELLER' AND x.buyer_id=?))",
        (user['id'], user['id']),
    )
    purchases = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE buyer_id=? AND status='COMPLETED'", (user['id'],))
    sales = await fetchone(session, "SELECT COALESCE(SUM(amount),0) AS s FROM deals WHERE seller_id=? AND status='COMPLETED'", (user['id'],))
    reviews = await fetchone(session, 'SELECT COUNT(*) AS c, COALESCE(AVG(stars),0) AS avg FROM reviews WHERE to_user_id=?', (user['id'],))

    await message.answer(
        f"🧽 User: @{user['username'] or user['tg_id']}\n"
        f"🪪 ID: {user['tg_id']}\n"
        f"💵 Balance: {Decimal(str(wallet['available_balance'])):.2f}$\n\n"
        f"🤝 Completed deals: {completed['c']}\n"
        f"⚖ Disputes lost: {disputes_lost['c']}\n\n"
        f"📈 Total purchases: {Decimal(str(purchases['s'])):.2f}$\n"
        f"📉 Total sales: {Decimal(str(sales['s'])):.2f}$\n\n"
        f"🗂️ Rating: {reviews['c']} reviews | {Decimal(str(reviews['avg'])):.1f} ⭐"
    )
