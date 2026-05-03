from decimal import Decimal

from app.db.repo import fetchone


async def get_wallet(conn, user_id: int) -> dict | None:
    return await fetchone(conn, 'SELECT * FROM wallets WHERE user_id=?', (user_id,))


async def move_available_to_frozen(conn, user_id: int, amount: Decimal) -> bool:
    wallet = await get_wallet(conn, user_id)
    if not wallet or Decimal(str(wallet['available_balance'])) < amount:
        return False
    await conn.execute(
        'UPDATE wallets SET available_balance=available_balance-?, frozen_balance=frozen_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (float(amount), float(amount), user_id),
    )
    return True


async def release_frozen_to_available(conn, user_id: int, amount: Decimal) -> bool:
    wallet = await get_wallet(conn, user_id)
    if not wallet or Decimal(str(wallet['frozen_balance'])) < amount:
        return False
    await conn.execute(
        'UPDATE wallets SET frozen_balance=frozen_balance-?, available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (float(amount), float(amount), user_id),
    )
    return True


async def transfer_from_frozen(conn, from_user_id: int, to_user_id: int, amount: Decimal) -> bool:
    from_wallet = await get_wallet(conn, from_user_id)
    if not from_wallet or Decimal(str(from_wallet['frozen_balance'])) < amount:
        return False
    await conn.execute(
        'UPDATE wallets SET frozen_balance=frozen_balance-?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (float(amount), from_user_id),
    )
    await conn.execute(
        'UPDATE wallets SET available_balance=available_balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (float(amount), to_user_id),
    )
    return True


async def deduct_frozen(conn, user_id: int, amount: Decimal) -> bool:
    wallet = await get_wallet(conn, user_id)
    if not wallet or Decimal(str(wallet['frozen_balance'])) < amount:
        return False
    await conn.execute(
        'UPDATE wallets SET frozen_balance=frozen_balance-?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?',
        (float(amount), user_id),
    )
    return True
