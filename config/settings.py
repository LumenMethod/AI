import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")  # @human2035

    # Anthropic Claude
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./human2035.db")

    # Subscription
    PRO_MONTHLY_PRICE: int = 490    # рублей
    EXPERT_MONTHLY_PRICE: int = 1990
    FREE_DAILY_LIMIT: int = 3       # бесплатных AI-запросов в день

    # Admin
    ADMIN_IDS: list = None

    def __post_init__(self):
        admin_raw = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = [int(x) for x in admin_raw.split(",") if x.strip().isdigit()]


settings = Settings()
