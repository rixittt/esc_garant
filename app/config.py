from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str
    database_url: str = 'sqlite+aiosqlite:///./bot.db'

    admin_ids: List[int] = []
    superadmin_ids: List[int] = []
    support_admin_username: str = 'admin'

    min_deal_amount: float = 1.0
    min_withdraw_amount: float = 1.0
    withdraw_fee_percent: float = 2.0
    pending_deal_timeout_hours: int = 24

    cryptobot_token: str | None = None
    cryptobot_api_base: str = 'https://pay.crypt.bot/api'

    @field_validator('admin_ids', 'superadmin_ids', mode='before')
    @classmethod
    def _parse_ids(cls, value: str | list[int]) -> list[int]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [int(x.strip()) for x in str(value).split(',') if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
