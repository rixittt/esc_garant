import json
from datetime import datetime
from decimal import Decimal

from app.db.repo import fetchone
from app.services.audit import log_action
from app.services.wallet import release_frozen_to_available, transfer_from_frozen


async def open_dispute(conn, actor_id: int, deal: dict, reason: str, attachments: dict | None = None):
    if deal['status'] != 'ACTIVE':
        return None
    await conn.execute('UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', ('DISPUTE', deal['id']))
    await conn.execute(
        'INSERT INTO disputes(deal_id, opened_by, reason_text, status) VALUES(?, ?, ?, ?)',
        (deal['id'], actor_id, reason, 'OPEN'),
    )
    dispute = await fetchone(conn, 'SELECT * FROM disputes WHERE deal_id=?', (deal['id'],))
    await conn.execute(
        'INSERT INTO dispute_messages(dispute_id, sender_id, text, attachments_json) VALUES(?, ?, ?, ?)',
        (dispute['id'], actor_id, reason, json.dumps(attachments or {})),
    )
    await log_action(conn, actor_id, 'dispute_opened', 'deal', deal['id'], {'reason': reason})
    return dispute


async def get_dispute_by_deal(conn, deal_id: int):
    return await fetchone(conn, 'SELECT * FROM disputes WHERE deal_id=?', (deal_id,))


async def resolve_buyer(conn, admin_id: int, deal: dict, dispute: dict):
    if deal['status'] not in {'DISPUTE', 'DISPUTE_WAITING'}:
        return False
    ok = await release_frozen_to_available(conn, deal['buyer_id'], Decimal(str(deal['amount'])))
    if not ok:
        return False
    await conn.execute('UPDATE deals SET status=? WHERE id=?', ('COMPLETED', deal['id']))
    await conn.execute(
        'UPDATE disputes SET status=?, resolution_type=?, resolved_by=?, resolved_at=? WHERE id=?',
        ('RESOLVED', 'BUYER', admin_id, datetime.utcnow().isoformat(), dispute['id']),
    )
    return True


async def resolve_seller(conn, admin_id: int, deal: dict, dispute: dict):
    if deal['status'] not in {'DISPUTE', 'DISPUTE_WAITING'}:
        return False
    ok = await transfer_from_frozen(conn, deal['buyer_id'], deal['seller_id'], Decimal(str(deal['amount'])))
    if not ok:
        return False
    await conn.execute('UPDATE deals SET status=? WHERE id=?', ('COMPLETED', deal['id']))
    await conn.execute(
        'UPDATE disputes SET status=?, resolution_type=?, resolved_by=?, resolved_at=? WHERE id=?',
        ('RESOLVED', 'SELLER', admin_id, datetime.utcnow().isoformat(), dispute['id']),
    )
    return True


async def resolve_split(conn, admin_id: int, deal: dict, dispute: dict):
    if deal['status'] not in {'DISPUTE', 'DISPUTE_WAITING'}:
        return False
    amount = Decimal(str(deal['amount']))
    half = (amount / Decimal('2')).quantize(Decimal('0.01'))
    rest = amount - half
    ok1 = await transfer_from_frozen(conn, deal['buyer_id'], deal['seller_id'], half)
    ok2 = await release_frozen_to_available(conn, deal['buyer_id'], rest)
    if not (ok1 and ok2):
        return False
    await conn.execute('UPDATE deals SET status=? WHERE id=?', ('COMPLETED', deal['id']))
    await conn.execute(
        'UPDATE disputes SET status=?, resolution_type=?, resolved_by=?, resolved_at=? WHERE id=?',
        ('RESOLVED', 'SPLIT', admin_id, datetime.utcnow().isoformat(), dispute['id']),
    )
    return True


async def request_more_info(conn, admin_id: int, deal: dict, dispute: dict, target: str, text: str):
    if deal['status'] != 'DISPUTE':
        return False
    await conn.execute('UPDATE deals SET status=? WHERE id=?', ('DISPUTE_WAITING', deal['id']))
    await conn.execute('UPDATE disputes SET status=? WHERE id=?', ('WAITING_INFO', dispute['id']))
    await log_action(conn, admin_id, 'dispute_more_info', 'deal', deal['id'], {'target': target, 'text': text})
    return True


async def resume_deal(conn, admin_id: int, deal: dict, dispute: dict):
    if deal['status'] not in {'DISPUTE', 'DISPUTE_WAITING'}:
        return False
    await conn.execute('UPDATE deals SET status=? WHERE id=?', ('ACTIVE', deal['id']))
    await conn.execute(
        'UPDATE disputes SET status=?, resolution_type=?, resolved_by=?, resolved_at=? WHERE id=?',
        ('CANCELLED', 'RESUME', admin_id, datetime.utcnow().isoformat(), dispute['id']),
    )
    return True
