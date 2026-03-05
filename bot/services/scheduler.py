"""Автоматический постинг в Telegram-каналы экосистемы "Человек 2035".

Поддержка мультиязычности: каждая ветка публикует на своих языках
в соответствующие каналы согласно BRANCH_LANGUAGES и BRANCH_CHANNELS в настройках.
"""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from bot.services.claude_ai import generate_daily_insight
from bot.services.content_generator import (
    generate_branch_post,
    generate_morning_digest,
    generate_evening_digest,
)
from bot.services.news_aggregator import fetch_news, fetch_all_news
from config.settings import settings

logger = logging.getLogger(__name__)

# Отслеживание тем, опубликованных сегодня (для вечернего дайджеста)
_posted_today: list[str] = []


def _get_branch_channels(branch: str) -> dict[str, str]:
    """
    Возвращает {lang: channel_id} для ветки из BRANCH_CHANNELS.
    Если BRANCH_CHANNELS не задан — фолбек на старые CHANNEL_* переменные (ru).
    """
    configured = settings.BRANCH_CHANNELS.get(branch)
    if configured:
        return configured

    # Фолбек: одиночный канал на русском
    attr_map = {
        "health":   "CHANNEL_HEALTH",
        "finance":  "CHANNEL_FINANCE",
        "tech":     "CHANNEL_TECH",
        "news":     "CHANNEL_NEWS",
        "edu":      "CHANNEL_EDU",
    }
    attr = attr_map.get(branch)
    channel = getattr(settings, attr, "") if attr else ""
    return {"ru": channel} if channel else {}


def _get_branch_languages(branch: str) -> list[str]:
    """
    Возвращает список языков для ветки из BRANCH_LANGUAGES.
    Фолбек — ["ru"].
    """
    return settings.BRANCH_LANGUAGES.get(branch) or ["ru"]


async def _send_to_channel(bot: Bot, channel: str, text: str) -> bool:
    """Отправляет текст в Telegram-канал."""
    if not channel:
        return False
    try:
        await bot.send_message(channel, text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Failed to post to {channel}: {e}")
        return False


# ──────────────────────────────────────────────
# Общая логика мультиязычного постинга ветки
# ──────────────────────────────────────────────

async def _post_branch(bot: Bot, branch: str) -> str | None:
    """
    Генерирует и публикует пост для всех языков ветки.
    Возвращает тему для вечернего дайджеста (строку) или None.
    """
    languages = _get_branch_languages(branch)
    channels = _get_branch_channels(branch)

    if not channels:
        logger.debug(f"No channels configured for branch '{branch}', skipping")
        return None

    # Получаем одну новость (одинаковую для всех языков — переводит Claude)
    news_items = await asyncio.get_event_loop().run_in_executor(
        None, fetch_news, branch, 1
    )
    news = news_items[0] if news_items else None

    topic = news.title if news else None
    published_any = False

    for lang in languages:
        channel = channels.get(lang)
        if not channel:
            logger.debug(f"No channel for branch='{branch}' lang='{lang}', skipping")
            continue
        try:
            text = await generate_branch_post(branch, news, language=lang)
            ok = await _send_to_channel(bot, channel, text)
            if ok:
                published_any = True
                logger.info(f"Posted branch='{branch}' lang='{lang}' → {channel}")
        except Exception as e:
            logger.error(f"Branch post error branch='{branch}' lang='{lang}': {e}")

    return topic if published_any else None


# ──────────────────────────────────────────────
# Задачи планировщика
# ──────────────────────────────────────────────

async def task_morning_news(bot: Bot):
    """06:00 — Дайджест новостей за ночь → главный канал (все языки)."""
    if not settings.CHANNEL_ID:
        return
    try:
        all_news = await asyncio.get_event_loop().run_in_executor(None, fetch_all_news, 2)
        # Утренний дайджест публикуем на языке главного канала (ru по умолчанию)
        main_langs = settings.BRANCH_LANGUAGES.get("main", ["ru"])
        for lang in main_langs:
            text = await generate_morning_digest(all_news, language=lang)
            await _send_to_channel(bot, settings.CHANNEL_ID, text)
        logger.info("Morning news digest posted")
    except Exception as e:
        logger.error(f"task_morning_news failed: {e}")


async def task_daily_insight(bot: Bot):
    """07:00 — Инсайт дня → главный канал."""
    if not settings.CHANNEL_ID:
        return
    try:
        insight = await generate_daily_insight()
        await bot.send_message(settings.CHANNEL_ID, insight, parse_mode="Markdown")
        _posted_today.append("💡 Инсайт дня")
        logger.info("Daily insight posted")
    except Exception as e:
        logger.error(f"task_daily_insight failed: {e}")


async def task_health_post(bot: Bot):
    """10:00 — Health-пост (все языки ветки)."""
    from bot.services.content_generator import BRANCH_PERSONAS
    topic = await _post_branch(bot, "health")
    if topic:
        _posted_today.append(f"{BRANCH_PERSONAS['health']['emoji']} {topic}")


async def task_finance_post(bot: Bot):
    """12:00 — Finance-пост (все языки ветки)."""
    from bot.services.content_generator import BRANCH_PERSONAS
    topic = await _post_branch(bot, "finance")
    if topic:
        _posted_today.append(f"{BRANCH_PERSONAS['finance']['emoji']} {topic}")


async def task_tech_post(bot: Bot):
    """15:00 — Tech-пост (все языки ветки)."""
    from bot.services.content_generator import BRANCH_PERSONAS
    topic = await _post_branch(bot, "tech")
    if topic:
        _posted_today.append(f"{BRANCH_PERSONAS['tech']['emoji']} {topic}")


async def task_edu_post(bot: Bot):
    """17:00 — Образовательный пост (все языки ветки)."""
    from bot.services.content_generator import BRANCH_PERSONAS
    topic = await _post_branch(bot, "edu")
    if topic:
        _posted_today.append(f"{BRANCH_PERSONAS['edu']['emoji']} {topic}")


async def task_evening_digest(bot: Bot):
    """20:00 — Вечерний дайджест → главный канал."""
    if not settings.CHANNEL_ID:
        return
    try:
        main_langs = settings.BRANCH_LANGUAGES.get("main", ["ru"])
        for lang in main_langs:
            text = await generate_evening_digest(list(_posted_today), language=lang)
            await _send_to_channel(bot, settings.CHANNEL_ID, text)
        _posted_today.clear()
        logger.info("Evening digest posted")
    except Exception as e:
        logger.error(f"task_evening_digest failed: {e}")


# ──────────────────────────────────────────────
# Расписание
# ──────────────────────────────────────────────

_SCHEDULE: list[tuple[int, int, str]] = [
    (6,  0,  "morning_news"),
    (7,  0,  "daily_insight"),
    (10, 0,  "health"),
    (12, 0,  "finance"),
    (15, 0,  "tech"),
    (17, 0,  "edu"),
    (20, 0,  "evening_digest"),
]

_TASK_MAP = {
    "morning_news":   task_morning_news,
    "daily_insight":  task_daily_insight,
    "health":         task_health_post,
    "finance":        task_finance_post,
    "tech":           task_tech_post,
    "edu":            task_edu_post,
    "evening_digest": task_evening_digest,
}


async def run_scheduler(bot: Bot):
    """Основной планировщик — проверяет расписание каждую минуту."""
    branch_count = len(settings.BRANCH_LANGUAGES) or 5
    lang_count = sum(len(v) for v in settings.BRANCH_LANGUAGES.values()) or 1
    logger.info(f"Scheduler started — {branch_count} branches, {lang_count} language channels")
    fired_today: dict[str, object] = {}

    while True:
        now = datetime.now()
        today = now.date()

        for hour, minute, name in _SCHEDULE:
            if now.hour == hour and now.minute == minute and fired_today.get(name) != today:
                fired_today[name] = today
                fn = _TASK_MAP[name]
                asyncio.create_task(fn(bot))
                logger.info(f"Scheduled task fired: {name} at {hour:02d}:{minute:02d}")

        if now.hour == 0 and now.minute == 0:
            fired_today.clear()

        await asyncio.sleep(60)
