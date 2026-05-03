import aiosqlite

from app.config import get_settings

settings = get_settings()


def _sqlite_path() -> str:
    url = settings.database_url
    if url.startswith('sqlite+aiosqlite:///'):
        return url.replace('sqlite+aiosqlite:///', '', 1)
    if url.startswith('sqlite:///'):
        return url.replace('sqlite:///', '', 1)
    return 'bot.db'


async def open_connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(_sqlite_path())
    conn.row_factory = aiosqlite.Row
    return conn
