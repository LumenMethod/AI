"""RSS-агрегатор новостей для контент-веток "Человек 2035"."""
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import feedparser

logger = logging.getLogger(__name__)

# RSS-источники по категориям
RSS_SOURCES = {
    "health": [
        "https://www.who.int/rss-feeds/news-russian.xml",
        "https://medportal.ru/rss/",
        "https://www.healthline.com/rss/news",
    ],
    "finance": [
        "https://www.rbc.ru/rss/",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://coindesk.com/arc/outboundfeeds/rss/",
    ],
    "tech": [
        "https://habr.com/ru/rss/best/daily/",
        "https://feeds.feedburner.com/TechCrunch",
        "https://www.technologyreview.com/feed/",
    ],
    "news": [
        "https://feeds.bbci.co.uk/russian/rss.xml",
        "https://www.rbc.ru/rss/",
        "https://lenta.ru/rss/",
    ],
    "edu": [
        "https://habr.com/ru/rss/flows/develop/all/",
        "https://feeds.feedburner.com/edutopia",
        "https://www.edx.org/rss",
    ],
}

# Хранилище хешей уже виденных новостей (in-memory, сбрасывается при рестарте)
_seen_hashes: set[str] = set()


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    category: str
    published: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def content_hash(self) -> str:
        """Уникальный хеш по заголовку для дедупликации."""
        return hashlib.md5(self.title.encode("utf-8")).hexdigest()


def _parse_feed(url: str, category: str, limit: int = 5) -> list[NewsItem]:
    """Парсит один RSS-фид, возвращает новые (ещё не виденные) элементы."""
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            item = NewsItem(
                title=title,
                summary=entry.get("summary", entry.get("description", ""))[:500].strip(),
                link=entry.get("link", ""),
                category=category,
            )

            # Пропускаем дубли
            h = item.content_hash()
            if h in _seen_hashes:
                continue
            _seen_hashes.add(h)
            items.append(item)

    except Exception as e:
        logger.warning(f"RSS parse error [{url}]: {e}")
    return items


def fetch_news(category: str, limit: int = 3) -> list[NewsItem]:
    """
    Синхронно собирает свежие новости по категории из всех источников.
    Возвращает не более `limit` новых элементов.
    """
    sources = RSS_SOURCES.get(category, [])
    result: list[NewsItem] = []
    for url in sources:
        result.extend(_parse_feed(url, category, limit=limit))
        if len(result) >= limit:
            break
    return result[:limit]


def fetch_all_news(limit_per_category: int = 2) -> dict[str, list[NewsItem]]:
    """Собирает новости по всем категориям одним вызовом."""
    return {cat: fetch_news(cat, limit=limit_per_category) for cat in RSS_SOURCES}
