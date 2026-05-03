import asyncio

from app.db.session import open_connection
from app.services.deals import auto_cancel_expired_pending


async def tick() -> None:
    while True:
        conn = await open_connection()
        try:
            ids = await auto_cancel_expired_pending(conn)
            if ids:
                await conn.commit()
                print(f'Auto-cancelled expired deals: {ids}')
        finally:
            await conn.close()
        await asyncio.sleep(60)


if __name__ == '__main__':
    asyncio.run(tick())
