import json
import os
from dataclasses import dataclass, field


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

    # Notion (база знаний)
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")

    # Chroma (векторная БД)
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

    # Telegram — ветки
    CHANNEL_HEALTH: str = os.getenv("CHANNEL_HEALTH", "")
    CHANNEL_FINANCE: str = os.getenv("CHANNEL_FINANCE", "")
    CHANNEL_TECH: str = os.getenv("CHANNEL_TECH", "")
    CHANNEL_NEWS: str = os.getenv("CHANNEL_NEWS", "")
    CHANNEL_EDU: str = os.getenv("CHANNEL_EDU", "")

    # Meta (Instagram + Facebook)
    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    INSTAGRAM_ACCOUNT_ID: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    FACEBOOK_PAGE_ID: str = os.getenv("FACEBOOK_PAGE_ID", "")

    # OpenAI (DALL-E 3 изображения)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    IMAGE_CACHE_DIR: str = os.getenv("IMAGE_CACHE_DIR", "./image_cache")

    # X (Twitter) — developer.twitter.com → Projects & Apps → Keys
    TWITTER_API_KEY: str = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET: str = os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN: str = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_TOKEN_SECRET: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

    # TikTok — developers.tiktok.com → Manage Apps → Content Posting API
    TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")

    # YouTube Data API v3 — console.cloud.google.com → APIs → YouTube Data API v3
    # YOUTUBE_CREDENTIALS_JSON: содержимое client_secret_*.json (OAuth2 desktop app)
    # YOUTUBE_TOKEN_JSON: содержимое token.json после первой авторизации
    YOUTUBE_CREDENTIALS_JSON: str = os.getenv("YOUTUBE_CREDENTIALS_JSON", "")
    YOUTUBE_TOKEN_JSON: str = os.getenv("YOUTUBE_TOKEN_JSON", "")
    YOUTUBE_CHANNEL_ID: str = os.getenv("YOUTUBE_CHANNEL_ID", "")
    # public | unlisted | private
    YOUTUBE_DEFAULT_PRIVACY: str = os.getenv("YOUTUBE_DEFAULT_PRIVACY", "public")

    # Мультиязычность — языки по веткам (JSON)
    # Пример: {"health": ["en", "pl", "uk"], "tech": ["ru", "en"], "finance": ["ru"]}
    BRANCH_LANGUAGES: dict = field(default_factory=dict)

    # Каналы по веткам и языкам (JSON)
    # Пример: {"health": {"ru": "@human2035_health", "en": "@human2035_health_en"}}
    BRANCH_CHANNELS: dict = field(default_factory=dict)

    # Admin
    ADMIN_IDS: list = field(default_factory=list)

    def __post_init__(self):
        admin_raw = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = [int(x) for x in admin_raw.split(",") if x.strip().isdigit()]

        raw_langs = os.getenv("BRANCH_LANGUAGES", "")
        self.BRANCH_LANGUAGES = json.loads(raw_langs) if raw_langs else {}

        raw_channels = os.getenv("BRANCH_CHANNELS", "")
        self.BRANCH_CHANNELS = json.loads(raw_channels) if raw_channels else {}


settings = Settings()
