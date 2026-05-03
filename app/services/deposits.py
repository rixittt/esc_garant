from decimal import Decimal, ROUND_HALF_UP

import aiohttp

from app.config import get_settings
from app.db.repo import fetchone

settings = get_settings()
INVOICE_MARKUP_PERCENT = Decimal('3')


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


async def _api_call(method: str, payload: dict) -> dict:
    if not settings.cryptobot_token:
        raise RuntimeError('CRYPTOBOT_TOKEN is not configured')

    url = f"{settings.cryptobot_api_base}/{method}"
    headers = {'Crypto-Pay-API-Token': settings.cryptobot_token}
    async with aiohttp.ClientSession() as client:
        async with client.post(url, headers=headers, json=payload, timeout=20) as resp:
            raw_text = await resp.text()
            try:
                data = await resp.json(content_type=None)
            except Exception:
                raise RuntimeError(f'CryptoBot API returned non-JSON response (HTTP {resp.status}): {raw_text[:300]}')
            if not data.get('ok'):
                raise RuntimeError(f"CryptoBot API error: {data}")
            return data['result']


async def create_deposit_invoice(conn, user_id: int, amount_usd: Decimal) -> dict:
    amount_usd = _q(amount_usd)
    invoice_amount_usd = _q(amount_usd * (Decimal('100') + INVOICE_MARKUP_PERCENT) / Decimal('100'))
    result = await _api_call(
        'createInvoice',
        {
            'currency_type': 'fiat',
            'fiat': 'USD',
            'amount': str(invoice_amount_usd),
            'accepted_assets': 'USDT,TON,BTC,ETH,USDC,BNB',
            'description': f'Deposit for user {user_id}',
        },
    )
    invoice_id = result['invoice_id']
    pay_url = result['pay_url']
    await conn.execute(
        'INSERT INTO deposits(user_id, invoice_id, amount_usd, pay_url, status) VALUES(?, ?, ?, ?, ?)',
        (user_id, invoice_id, float(amount_usd), pay_url, 'ACTIVE'),
    )
    dep = await fetchone(conn, 'SELECT * FROM deposits WHERE invoice_id=?', (invoice_id,))
    dep['invoice_amount_usd'] = float(invoice_amount_usd)
    return dep


async def get_deposit(conn, deposit_id: int) -> dict | None:
    return await fetchone(conn, 'SELECT * FROM deposits WHERE id=?', (deposit_id,))


async def set_deposit_notify_message(conn, deposit_id: int, chat_id: int, message_id: int) -> None:
    await conn.execute(
        'UPDATE deposits SET notify_chat_id=?, notify_message_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
        (chat_id, message_id, deposit_id),
    )


async def cancel_deposit(conn, deposit_id: int, user_id: int) -> bool:
    dep = await get_deposit(conn, deposit_id)
    if not dep or dep['user_id'] != user_id or dep['credited']:
        return False
    await conn.execute("UPDATE deposits SET status='CANCELLED', updated_at=CURRENT_TIMESTAMP WHERE id=?", (deposit_id,))
    return True


async def _mark_deposit_paid_once(conn, deposit_id: int) -> bool:
    cur = await conn.execute(
        "UPDATE deposits SET status='PAID', credited=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND credited=0",
        (deposit_id,),
    )
    return cur.rowcount == 1


async def check_and_credit_deposit(conn, deposit_id: int, user_id: int) -> tuple[bool, str]:
    dep = await get_deposit(conn, deposit_id)
    if not dep or dep['user_id'] != user_id:
        return False, 'Deposit not found.'
    if dep['credited']:
        return True, 'Deposit already credited.'

    result = await _api_call('getInvoices', {'invoice_ids': str(dep['invoice_id'])})
    items = result.get('items', [])
    if not items:
        return False, 'Invoice not found in CryptoBot.'
    status = items[0].get('status')
    if status != 'paid':
        return False, f'Invoice status: {status}. Please complete payment first.'

    marked = await _mark_deposit_paid_once(conn, deposit_id)
    if not marked:
        return True, 'Deposit already credited.'
    await conn.execute(
        'UPDATE wallets SET available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (dep['amount_usd'], dep['user_id']),
    )
    return True, f"Deposit credited: ${Decimal(str(dep['amount_usd'])):.2f}"


async def process_webhook_paid_invoice(conn, invoice_id: int) -> tuple[bool, str]:
    dep = await fetchone(conn, 'SELECT * FROM deposits WHERE invoice_id=?', (invoice_id,))
    if not dep:
        return False, 'Deposit not found for invoice.'
    if dep['credited']:
        return True, 'Already credited.'

    marked = await _mark_deposit_paid_once(conn, dep['id'])
    if not marked:
        return True, 'Already credited.'
    await conn.execute(
        'UPDATE wallets SET available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (dep['amount_usd'], dep['user_id']),
    )
    return True, 'Credited via webhook.'
