import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import start, ai_chat, admin
from bot.services.database import init_db
from bot.services.scheduler import run_scheduler
from bot.services.knowledge_base import init_knowledge_base
from bot.services.rag_sync import sync_notion_to_kb, run_sync_scheduler
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not settings.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env файле")
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY не задан в .env файле")

    logger.info("Initializing database...")
    await init_db()

    logger.info("Initializing knowledge base...")
    await init_knowledge_base()

    # Первичная синхронизация из Notion (если токен задан)
    if settings.NOTION_TOKEN:
        logger.info("Initial Notion sync...")
        result = await sync_notion_to_kb()
        logger.info(f"Notion sync: {result}")
    else:
        logger.warning("NOTION_TOKEN not set — knowledge base will be empty")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(ai_chat.router)
    dp.include_router(admin.router)

    logger.info("Starting Human 2035 Bot...")

    asyncio.create_task(run_scheduler(bot))
    asyncio.create_task(run_sync_scheduler())  # авто-синхронизация каждые 6 часов

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
