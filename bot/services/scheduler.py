"""Автоматический постинг в Telegram-каналы экосистемы "Человек 2035"."""
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


def _channel(attr: str) -> str | None:
    """Возвращает ID канала из настроек или None."""
    return getattr(settings, attr, None) or None


async def _send(bot: Bot, channel_attr: str, text: str) -> bool:
    """Отправляет сообщение в канал, возвращает True при успехе."""
    channel = _channel(channel_attr)
    if not channel:
        logger.debug(f"Channel {channel_attr} not configured, skipping")
        return False
    try:
        await bot.send_message(channel, text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Failed to post to {channel_attr}: {e}")
        return False


# ──────────────────────────────────────────────
# Задачи планировщика
# ──────────────────────────────────────────────

async def task_morning_news(bot: Bot):
    """06:00 — Дайджест новостей за ночь → главный канал."""
    try:
        all_news = await asyncio.get_event_loop().run_in_executor(None, fetch_all_news, 2)
        text = await generate_morning_digest(all_news)
        await _send(bot, "CHANNEL_ID", text)
        logger.info("Morning news digest posted")
    except Exception as e:
        logger.error(f"task_morning_news failed: {e}")


async def task_daily_insight(bot: Bot):
    """07:00 — Инсайт дня (Markdown) → главный канал."""
    if not _channel("CHANNEL_ID"):
        return
    try:
        insight = await generate_daily_insight()
        channel = _channel("CHANNEL_ID")
        await bot.send_message(channel, insight, parse_mode="Markdown")
        _posted_today.append("Инсайт дня")
        logger.info("Daily insight posted")
    except Exception as e:
        logger.error(f"task_daily_insight failed: {e}")


async def task_health_post(bot: Bot):
    """10:00 — Health-пост → @human2035_health."""
    try:
        news_items = await asyncio.get_event_loop().run_in_executor(
            None, fetch_news, "health", 1
        )
        news = news_items[0] if news_items else None
        text = await generate_branch_post("health", news)
        await _send(bot, "CHANNEL_HEALTH", text)
        topic = news.title if news else "Здоровье дня"
        _posted_today.append(f"🧠 {topic}")
        logger.info("Health post sent")
    except Exception as e:
        logger.error(f"task_health_post failed: {e}")


async def task_finance_post(bot: Bot):
    """12:00 — Finance-пост → @human2035_finance."""
    try:
        news_items = await asyncio.get_event_loop().run_in_executor(
            None, fetch_news, "finance", 1
        )
        news = news_items[0] if news_items else None
        text = await generate_branch_post("finance", news)
        await _send(bot, "CHANNEL_FINANCE", text)
        topic = news.title if news else "Финансы дня"
        _posted_today.append(f"💰 {topic}")
        logger.info("Finance post sent")
    except Exception as e:
        logger.error(f"task_finance_post failed: {e}")


async def task_tech_post(bot: Bot):
    """15:00 — Tech-пост → @human2035_tech."""
    try:
        news_items = await asyncio.get_event_loop().run_in_executor(
            None, fetch_news, "tech", 1
        )
        news = news_items[0] if news_items else None
        text = await generate_branch_post("tech", news)
        await _send(bot, "CHANNEL_TECH", text)
        topic = news.title if news else "Технологии дня"
        _posted_today.append(f"🤖 {topic}")
        logger.info("Tech post sent")
    except Exception as e:
        logger.error(f"task_tech_post failed: {e}")


async def task_edu_post(bot: Bot):
    """17:00 — Образовательный пост → @human2035_edu."""
    try:
        news_items = await asyncio.get_event_loop().run_in_executor(
            None, fetch_news, "edu", 1
        )
        news = news_items[0] if news_items else None
        text = await generate_branch_post("edu", news)
        await _send(bot, "CHANNEL_EDU", text)
        topic = news.title if news else "Урок дня"
        _posted_today.append(f"🎓 {topic}")
        logger.info("Edu post sent")
    except Exception as e:
        logger.error(f"task_edu_post failed: {e}")


async def task_evening_digest(bot: Bot):
    """20:00 — Вечерний дайджест → главный канал."""
    try:
        text = await generate_evening_digest(list(_posted_today))
        await _send(bot, "CHANNEL_ID", text)
        _posted_today.clear()
        logger.info("Evening digest posted")
    except Exception as e:
        logger.error(f"task_evening_digest failed: {e}")


# ──────────────────────────────────────────────
# Расписание
# ──────────────────────────────────────────────

# (час, минута) → функция-задача
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
    "morning_news":  task_morning_news,
    "daily_insight": task_daily_insight,
    "health":        task_health_post,
    "finance":       task_finance_post,
    "tech":          task_tech_post,
    "edu":           task_edu_post,
    "evening_digest": task_evening_digest,
}


async def run_scheduler(bot: Bot):
    """Основной планировщик — проверяет расписание каждую минуту."""
    logger.info("Scheduler started (7 tasks/day)")
    fired_today: dict[str, object] = {}  # task_name → date

    while True:
        now = datetime.now()
        today = now.date()

        for hour, minute, name in _SCHEDULE:
            if now.hour == hour and now.minute == minute and fired_today.get(name) != today:
                fired_today[name] = today
                fn = _TASK_MAP[name]
                asyncio.create_task(fn(bot))
                logger.info(f"Scheduled task fired: {name} at {hour:02d}:{minute:02d}")

        # Сброс fired_today в полночь
        if now.hour == 0 and now.minute == 0:
            fired_today.clear()

        await asyncio.sleep(60)
