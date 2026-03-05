import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import start, ai_chat, admin
from bot.services.database import init_db
from bot.services.scheduler import run_scheduler
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

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(ai_chat.router)
    dp.include_router(admin.router)

    logger.info("Starting Human 2035 Bot...")

    # Запускаем планировщик параллельно
    asyncio.create_task(run_scheduler(bot))

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
