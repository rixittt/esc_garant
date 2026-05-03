import random
import sqlite3
import string
from datetime import datetime, timedelta
from decimal import Decimal

from app.config import get_settings
from app.db.repo import fetchall, fetchone
from app.services.audit import log_action
from app.services.settings import get_decimal
from app.services.wallet import move_available_to_frozen, release_frozen_to_available, transfer_from_frozen

settings = get_settings()


def _public_id() -> str:
    return 'de' + ''.join(random.choices(string.ascii_letters + string.digits, k=6))


async def find_user_by_username_or_id(conn, raw: str):
    raw = raw.strip()
    if raw.startswith('@'):
        raw = raw[1:]
    if raw.isdigit():
        return await fetchone(conn, 'SELECT * FROM users WHERE tg_id=?', (int(raw),))
    return await fetchone(conn, 'SELECT * FROM users WHERE username=?', (raw,))


async def create_deal(conn, buyer_id: int, seller_id: int, amount: Decimal, terms: str):
    if buyer_id == seller_id:
        return None
    min_deal = await get_decimal(conn, 'min_deal_amount', Decimal(str(settings.min_deal_amount)))
    if amount < min_deal:
        return None

    expires_at = (datetime.utcnow() + timedelta(hours=settings.pending_deal_timeout_hours)).isoformat()
    public_id = _public_id()
    await conn.execute(
        'INSERT INTO deals(public_id, buyer_id, seller_id, amount, terms, status, expires_at) VALUES(?, ?, ?, ?, ?, ?, ?)',
        (public_id, buyer_id, seller_id, float(amount), terms, 'PENDING', expires_at),
    )
    deal = await fetchone(conn, 'SELECT * FROM deals ORDER BY id DESC LIMIT 1')
    await log_action(conn, buyer_id, 'deal_created', 'deal', deal['id'], {'seller_id': seller_id, 'amount': str(amount)})
    return deal


async def get_deal(conn, deal_id: int):
    return await fetchone(conn, 'SELECT * FROM deals WHERE id=?', (deal_id,))


async def get_user_deals_page(conn, user_id: int, page: int, page_size: int = 5):
    offset = max(page - 1, 0) * page_size
    deals = await fetchall(
        conn,
        'SELECT * FROM deals WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT ? OFFSET ?',
        (user_id, user_id, page_size, offset),
    )
    count_row = await fetchone(conn, 'SELECT COUNT(*) AS c FROM deals WHERE buyer_id=? OR seller_id=?', (user_id, user_id))
    total = count_row['c'] if count_row else 0
    total_pages = max((total + page_size - 1) // page_size, 1)
    return deals, total_pages


async def accept_deal(conn, actor_tg_id: int, deal: dict) -> bool:
    actor = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor or actor['id'] not in {deal['buyer_id'], deal['seller_id']} or deal['status'] != 'PENDING':
        return False
    ok = await move_available_to_frozen(conn, deal['buyer_id'], Decimal(str(deal['amount'])))
    if not ok:
        return False
    await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('ACTIVE', deal['id']))
    return True


async def decline_deal(conn, actor_tg_id: int, deal: dict) -> bool:
    actor = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor or actor['id'] not in {deal['buyer_id'], deal['seller_id']} or deal['status'] != 'PENDING':
        return False
    await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('CANCELLED', deal['id']))
    return True


async def start_complete_request(conn, actor_tg_id: int, deal: dict) -> bool:
    if deal['status'] != 'ACTIVE':
        return False
    actor_user = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor_user or actor_user['id'] not in {deal['buyer_id'], deal['seller_id']}:
        return False

    await conn.execute('UPDATE deals SET complete_requested_by=? WHERE id=?', (actor_user['id'], deal['id']))
    return True


async def confirm_complete_request(conn, actor_tg_id: int, deal: dict) -> tuple[bool, bool]:
    """returns (ok, completed_now)."""
    if deal['status'] != 'ACTIVE':
        return False, False
    actor_user = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor_user or actor_user['id'] not in {deal['buyer_id'], deal['seller_id']}:
        return False, False

    if actor_user['id'] == deal['buyer_id']:
        await conn.execute('UPDATE deals SET buyer_confirmed=1 WHERE id=?', (deal['id'],))
    else:
        await conn.execute('UPDATE deals SET seller_confirmed=1 WHERE id=?', (deal['id'],))

    refreshed = await get_deal(conn, deal['id'])
    if refreshed['buyer_confirmed'] and refreshed['seller_confirmed']:
        ok = await transfer_from_frozen(conn, refreshed['buyer_id'], refreshed['seller_id'], Decimal(str(refreshed['amount'])))
        if not ok:
            return False, False
        await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('COMPLETED', refreshed['id']))
        return True, True
    return True, False


async def cancel_deal(conn, actor_tg_id: int, deal: dict) -> bool:
    seller = await fetchone(conn, 'SELECT tg_id FROM users WHERE id=?', (deal['seller_id'],))
    if not seller or seller['tg_id'] != actor_tg_id or deal['status'] != 'ACTIVE':
        return False
    ok = await release_frozen_to_available(conn, deal['buyer_id'], Decimal(str(deal['amount'])))
    if not ok:
        return False
    await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('CANCELLED', deal['id']))
    return True


async def start_cancel_request(conn, actor_tg_id: int, deal: dict) -> bool:
    if deal['status'] != 'ACTIVE':
        return False
    actor_user = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor_user or actor_user['id'] not in {deal['buyer_id'], deal['seller_id']}:
        return False
    await conn.execute('UPDATE deals SET cancel_requested_by=? WHERE id=?', (actor_user['id'], deal['id']))
    return True


async def confirm_cancel_request(conn, actor_tg_id: int, deal: dict) -> tuple[bool, bool]:
    if deal['status'] != 'ACTIVE':
        return False, False
    actor_user = await fetchone(conn, 'SELECT id FROM users WHERE tg_id=?', (actor_tg_id,))
    if not actor_user or actor_user['id'] not in {deal['buyer_id'], deal['seller_id']}:
        return False, False
    if actor_user['id'] == deal['buyer_id']:
        await conn.execute('UPDATE deals SET buyer_cancel_confirmed=1 WHERE id=?', (deal['id'],))
    else:
        await conn.execute('UPDATE deals SET seller_cancel_confirmed=1 WHERE id=?', (deal['id'],))

    refreshed = await get_deal(conn, deal['id'])
    if refreshed['buyer_cancel_confirmed'] and refreshed['seller_cancel_confirmed']:
        ok = await release_frozen_to_available(conn, refreshed['buyer_id'], Decimal(str(refreshed['amount'])))
        if not ok:
            return False, False
        await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('CANCELLED', refreshed['id']))
        return True, True
    return True, False


async def save_deal_message(conn, deal_id: int, sender_id: int, recipient_id: int, text: str) -> None:
    await conn.execute('INSERT INTO deal_messages(deal_id, sender_id, recipient_id, text) VALUES(?, ?, ?, ?)', (deal_id, sender_id, recipient_id, text))


async def leave_review(conn, deal_id: int, from_user_id: int, to_user_id: int, stars: int) -> bool:
    existing = await fetchone(conn, 'SELECT id FROM reviews WHERE deal_id=? AND from_user_id=?', (deal_id, from_user_id))
    if existing:
        return False
    try:
        await conn.execute(
            'INSERT INTO reviews(deal_id, from_user_id, to_user_id, stars) VALUES(?, ?, ?, ?)',
            (deal_id, from_user_id, to_user_id, stars),
        )
    except sqlite3.IntegrityError:
        return False
    return True


async def auto_cancel_expired_pending(conn, limit: int = 100) -> list[int]:
    rows = await fetchall(
        conn,
        "SELECT * FROM deals WHERE status='PENDING' AND expires_at <= ? LIMIT ?",
        (datetime.utcnow().isoformat(), limit),
    )
    cancelled = []
    for deal in rows:
        ok = await release_frozen_to_available(conn, deal['buyer_id'], Decimal(str(deal['amount'])))
        if ok:
            await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('CANCELLED', deal['id']))
            cancelled.append(deal['id'])
    return cancelled
