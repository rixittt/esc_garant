from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.db.repo import fetchall, fetchone
from app.services.settings import get_decimal
from app.services.wallet import deduct_frozen, move_available_to_frozen, release_frozen_to_available


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


async def create_withdraw_request(conn, user_id: int, amount: Decimal, requisites: str):
    min_withdraw = await get_decimal(conn, 'min_withdraw_amount', Decimal('4.50'))
    if amount < min_withdraw:
        return None

    fee_percent = await get_decimal(conn, 'withdraw_fee_percent', Decimal('0'))
    fee_fixed = await get_decimal(conn, 'withdraw_fee_amount', Decimal('0.50'))
    percent_fee = _q(amount * fee_percent / Decimal('100'))
    fee_amount = _q(fee_fixed + percent_fee)
    net_amount = _q(amount - fee_amount)
    if net_amount <= 0:
        return None

    await conn.execute(
        'INSERT INTO withdraw_requests(user_id, amount, fee_percent, fee_amount, net_amount, requisites, status) VALUES(?, ?, ?, ?, ?, ?, ?)',
        (user_id, float(_q(amount)), float(fee_percent), float(fee_amount), float(net_amount), requisites, 'PENDING'),
    )
    req = await fetchone(conn, 'SELECT * FROM withdraw_requests ORDER BY id DESC LIMIT 1')
    ok = await move_available_to_frozen(conn, user_id, _q(amount))
    return req if ok else None


async def list_pending_withdraws(conn, limit: int = 20, offset: int = 0):
    return await fetchall(
        conn,
        "SELECT * FROM withdraw_requests WHERE status='PENDING' ORDER BY id ASC LIMIT ? OFFSET ?",
        (limit, offset),
    )


async def get_withdraw(conn, withdraw_id: int):
    return await fetchone(conn, 'SELECT * FROM withdraw_requests WHERE id=?', (withdraw_id,))


async def approve_withdraw(conn, admin_id: int, req: dict, tx_info: str):
    if req['status'] != 'PENDING':
        return False
    ok = await deduct_frozen(conn, req['user_id'], Decimal(str(req['amount'])))
    if not ok:
        return False
    await conn.execute(
        'UPDATE withdraw_requests SET status=?, tx_info=?, processed_by=?, processed_at=? WHERE id=?',
        ('APPROVED', tx_info, admin_id, datetime.utcnow().isoformat(), req['id']),
    )
    return True


async def reject_withdraw(conn, admin_id: int, req: dict):
    if req['status'] != 'PENDING':
        return False
    ok = await release_frozen_to_available(conn, req['user_id'], Decimal(str(req['amount'])))
    if not ok:
        return False
    await conn.execute(
        'UPDATE withdraw_requests SET status=?, processed_by=?, processed_at=? WHERE id=?',
        ('REJECTED', admin_id, datetime.utcnow().isoformat(), req['id']),
    )
    return True
