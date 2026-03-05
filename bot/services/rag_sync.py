"""Синхронизация Notion → Chroma. Запускается по расписанию и вручную."""
import asyncio
import logging
from bot.services.notion_loader import NotionLoader
from bot.services.knowledge_base import get_kb
from config.settings import settings

logger = logging.getLogger(__name__)


async def sync_notion_to_kb(full_resync: bool = False) -> dict:
    """
    Синхронизировать все страницы Notion в векторную базу знаний.
    full_resync=True — полная очистка и переиндексация.
    Возвращает статистику.
    """
    kb = get_kb()
    if not kb:
        return {"error": "База знаний не инициализирована"}

    if not settings.NOTION_TOKEN:
        return {"error": "NOTION_TOKEN не задан в .env"}

    loader = NotionLoader(settings.NOTION_TOKEN)

    logger.info("Starting Notion sync...")
    documents = await loader.load_all_documents()

    if not documents:
        return {"synced": 0, "message": "Страниц в Notion не найдено. Проверь, что интеграция добавлена к страницам."}

    loop = asyncio.get_event_loop()

    if full_resync:
        await loop.run_in_executor(None, kb.clear)
        logger.info("Knowledge base cleared for full resync")

    await loop.run_in_executor(None, kb.add_documents, documents)

    stats = kb.get_stats()
    return {
        "synced_pages": len(documents),
        "total_chunks": stats["total_chunks"],
        "pages": [d["title"] for d in documents],
    }


async def run_sync_scheduler():
    """Автосинхронизация каждые 6 часов."""
    logger.info("Notion sync scheduler started")
    while True:
        await asyncio.sleep(6 * 3600)  # 6 часов
        try:
            result = await sync_notion_to_kb()
            logger.info(f"Auto-sync complete: {result}")
        except Exception as e:
            logger.error(f"Auto-sync failed: {e}")
