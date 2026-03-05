"""Команды для администраторов."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select, func
from bot.services.database import async_session, User
from bot.services.claude_ai import generate_channel_post
from bot.services.scheduler import post_daily_insight, post_weekly_content
from bot.services.rag_sync import sync_notion_to_kb
from config.settings import settings

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("stats"))
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session() as session:
        total = await session.scalar(select(func.count(User.id)))
        pro_count = await session.scalar(select(func.count(User.id)).where(User.is_pro == True))
        expert_count = await session.scalar(select(func.count(User.id)).where(User.is_expert == True))

    monthly_revenue = pro_count * settings.PRO_MONTHLY_PRICE + expert_count * settings.EXPERT_MONTHLY_PRICE

    await message.answer(
        f"📊 <b>Статистика платформы</b>\n\n"
        f"👥 Всего пользователей: <b>{total}</b>\n"
        f"🔥 Pro подписчиков: <b>{pro_count}</b>\n"
        f"💎 Expert подписчиков: <b>{expert_count}</b>\n\n"
        f"💰 Месячный доход (расчётный): <b>{monthly_revenue:,}₽</b>",
        parse_mode="HTML",
    )


@router.message(Command("post"))
async def admin_post(message: Message):
    """Команда: /post <тема> — создать и опубликовать пост."""
    if not is_admin(message.from_user.id):
        return

    topic = message.text.removeprefix("/post").strip()
    if not topic:
        await message.answer("Использование: /post <тема поста>")
        return

    msg = await message.answer("⏳ Генерирую пост...")
    post_text = await generate_channel_post(topic)
    await msg.edit_text(f"📝 <b>Превью поста:</b>\n\n{post_text}", parse_mode="HTML")

    # Отправляем в канал
    from aiogram import Bot
    bot: Bot = message.bot
    if settings.CHANNEL_ID:
        await bot.send_message(settings.CHANNEL_ID, post_text, parse_mode="HTML")
        await message.answer("✅ Пост опубликован в канале!")


@router.message(Command("sync"))
async def admin_sync(message: Message):
    """Синхронизировать базу знаний из Notion."""
    if not is_admin(message.from_user.id):
        return

    full = "--full" in message.text
    msg = await message.answer("⏳ Синхронизирую базу знаний из Notion...")

    result = await sync_notion_to_kb(full_resync=full)

    if "error" in result:
        await msg.edit_text(f"❌ Ошибка: {result['error']}")
        return

    pages_list = "\n".join(f"  • {p}" for p in result.get("pages", [])[:10])
    if len(result.get("pages", [])) > 10:
        pages_list += f"\n  ... и ещё {len(result['pages']) - 10}"

    await msg.edit_text(
        f"✅ <b>База знаний обновлена</b>\n\n"
        f"📄 Страниц загружено: <b>{result['synced_pages']}</b>\n"
        f"🧩 Чанков в индексе: <b>{result['total_chunks']}</b>\n\n"
        f"<b>Страницы:</b>\n{pages_list}",
        parse_mode="HTML",
    )


@router.message(Command("kbstats"))
async def admin_kb_stats(message: Message):
    """Статистика базы знаний."""
    if not is_admin(message.from_user.id):
        return
    from bot.services.knowledge_base import get_kb
    kb = get_kb()
    if not kb:
        await message.answer("База знаний не инициализирована")
        return
    stats = kb.get_stats()
    await message.answer(
        f"📚 <b>База знаний</b>\n\n"
        f"Чанков в индексе: <b>{stats['total_chunks']}</b>\n\n"
        f"Команды:\n"
        f"/sync — обновить из Notion\n"
        f"/sync --full — полная переиндексация",
        parse_mode="HTML",
    )


@router.message(Command("insight"))
async def admin_insight(message: Message):
    """Срочно опубликовать инсайт дня."""
    if not is_admin(message.from_user.id):
        return
    await post_daily_insight(message.bot)
    await message.answer("✅ Инсайт опубликован!")


@router.message(Command("setpro"))
async def admin_set_pro(message: Message):
    """Команда: /setpro <user_id> — выдать Pro подписку."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /setpro <telegram_user_id>")
        return

    target_id = int(parts[1])
    from sqlalchemy import update
    async with async_session() as session:
        await session.execute(update(User).where(User.telegram_id == target_id).values(is_pro=True))
        await session.commit()

    await message.answer(f"✅ Пользователю {target_id} выдана Pro подписка")
