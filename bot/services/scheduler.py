"""Автоматический постинг в Telegram канал."""
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from bot.services.claude_ai import generate_daily_insight, generate_channel_post
from config.settings import settings

logger = logging.getLogger(__name__)

# Темы для автопостинга по дням недели
WEEKLY_TOPICS = {
    0: "Искусственный интеллект и будущее профессий — что нужно знать уже сегодня",
    1: "Биохакинг и долголетие: топ-5 привычек людей 2035 года",
    2: "Финансы будущего: как зарабатывать в мире автоматизации",
    3: "Нейротехнологии: как мы будем учиться и работать через 10 лет",
    4: "Психология будущего: как адаптировать мозг к постоянным переменам",
    5: "Зелёные технологии и новая экономика: возможности для каждого",
    6: "Итоги недели: 7 фактов о будущем, которые изменят твой взгляд на мир",
}


async def post_daily_insight(bot: Bot):
    """07:00 — Инсайт дня."""
    if not settings.CHANNEL_ID:
        return
    try:
        insight = await generate_daily_insight()
        await bot.send_message(settings.CHANNEL_ID, insight, parse_mode="Markdown")
        logger.info("Daily insight posted to channel")
    except Exception as e:
        logger.error(f"Failed to post daily insight: {e}")


async def post_weekly_content(bot: Bot):
    """17:00 — Тематический пост."""
    if not settings.CHANNEL_ID:
        return
    try:
        weekday = datetime.now().weekday()
        topic = WEEKLY_TOPICS.get(weekday, "Технологии будущего")
        post = await generate_channel_post(topic)
        await bot.send_message(settings.CHANNEL_ID, post, parse_mode="HTML")
        logger.info(f"Weekly content posted: {topic}")
    except Exception as e:
        logger.error(f"Failed to post weekly content: {e}")


async def run_scheduler(bot: Bot):
    """Основной планировщик. Проверяет время каждую минуту."""
    logger.info("Scheduler started")
    last_insight_date = None
    last_post_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # 07:00 — инсайт дня
        if now.hour == 7 and now.minute == 0 and last_insight_date != today:
            last_insight_date = today
            asyncio.create_task(post_daily_insight(bot))

        # 17:00 — тематический пост
        if now.hour == 17 and now.minute == 0 and last_post_date != today:
            last_post_date = today
            asyncio.create_task(post_weekly_content(bot))

        await asyncio.sleep(60)  # проверяем каждую минуту
