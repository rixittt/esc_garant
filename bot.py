import asyncio
import json
import logging
from decimal import Decimal

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db.init_db import init_db
from app.db.repo import fetchone
from app.db.session import open_connection
from app.handlers import admin, balance, common, deals, deposit, support, withdraw
from app.middlewares.ban_check import BanCheckMiddleware
from app.middlewares.db_session import DbSessionMiddleware
from app.services.deposits import process_webhook_paid_invoice

logger = logging.getLogger(__name__)


async def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.message.middleware(BanCheckMiddleware())

    dp.include_router(common.router)
    dp.include_router(balance.router)
    dp.include_router(deals.router)
    dp.include_router(withdraw.router)
    dp.include_router(deposit.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)
    return dp


async def cryptobot_webhook(request: web.Request) -> web.Response:
    bot: Bot | None = request.app.get('bot')
    try:
        raw_body = await request.read()
        body_text = raw_body.decode('utf-8', errors='replace')
    except Exception:
        logger.exception('CryptoBot webhook: failed to read body')
        return web.Response(status=400, text='Bad request')

    logger.info('CryptoBot webhook received: %s', body_text)

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        logger.warning('CryptoBot webhook invalid JSON')
        return web.Response(status=400, text='Invalid JSON')

    update_type = payload.get('update_type')
    update = payload.get('update') or payload.get('payload') or {}

    if update_type != 'invoice_paid':
        return web.json_response({'ok': True, 'ignored': True})

    invoice_id = update.get('invoice_id')
    if not invoice_id:
        logger.warning('CryptoBot webhook invoice_paid without invoice_id')
        return web.Response(status=400, text='Missing invoice_id')

    conn = await open_connection()
    try:
        dep = await fetchone(conn, 'SELECT * FROM deposits WHERE invoice_id=?', (int(invoice_id),))
        ok, text = await process_webhook_paid_invoice(conn, int(invoice_id))
        await conn.commit()
        logger.info('CryptoBot webhook processed invoice_id=%s ok=%s msg=%s', invoice_id, ok, text)
        if ok and dep and dep.get('notify_chat_id') and dep.get('notify_message_id') and bot:
            try:
                await bot.edit_message_text(
                    chat_id=dep['notify_chat_id'],
                    message_id=dep['notify_message_id'],
                    text=(
                        f"✅ Payment received successfully.\n"
                        f"Deposit credited: ${Decimal(str(dep['amount_usd'])):.2f}"
                    ),
                )
            except Exception:
                logger.exception('Failed to edit deposit invoice message for invoice_id=%s', invoice_id)
    except Exception:
        logger.exception('CryptoBot webhook processing failed for invoice_id=%s', invoice_id)
        return web.Response(status=500, text='Internal error')
    finally:
        await conn.close()
    return web.json_response({'ok': True})


async def run_webhook_server(bot: Bot) -> web.AppRunner | None:
    settings = get_settings()
    webhook_path = getattr(settings, 'cryptobot_webhook_path', '/cryptobot/webhook')
    webhook_host = getattr(settings, 'cryptobot_webhook_host', '0.0.0.0')
    webhook_port = int(getattr(settings, 'cryptobot_webhook_port', 8081))

    app = web.Application()
    app['bot'] = bot
    app.router.add_post(webhook_path, cryptobot_webhook)
    # Fallback for randomized/suffixed CryptoBot webhook URLs like /cryptobot/webhook-<token>.
    app.router.add_post('/cryptobot/{tail:.*}', cryptobot_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=webhook_host, port=webhook_port)
    await site.start()
    logger.info(
        'CryptoBot webhook server started on http://%s:%s%s',
        webhook_host,
        webhook_port,
        webhook_path,
    )
    return runner


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await init_db()
    webhook_runner = await run_webhook_server(bot)
    dp = await create_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        if webhook_runner:
            await webhook_runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
