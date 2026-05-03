from aiogram import Bot


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception:
        return


async def safe_send_photo(bot: Bot, chat_id: int, photo: str, caption: str | None = None, **kwargs) -> None:
    try:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)
    except Exception:
        return
