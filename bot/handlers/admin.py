"""Команды для администраторов платформы "Человек 2035"."""
from datetime import datetime

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select, func, update

from bot.services.database import (
    async_session, User,
    get_analytics, get_branch_last_post,
    get_active_sources, add_news_source, toggle_news_source,
)
from bot.services.content_generator import generate_branch_post, BRANCH_PERSONAS, BRANCH_META
from bot.services.scheduler import task_daily_insight
from bot.services.rag_sync import sync_notion_to_kb
from config.settings import settings

router = Router()

BRANCHES = list(BRANCH_META.keys())  # health, finance, tech, news, edu


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


def _ago(dt: datetime | None) -> str:
    if not dt:
        return "никогда"
    delta = datetime.utcnow() - dt
    h, m = divmod(int(delta.total_seconds() // 60), 60)
    if h:
        return f"{h}ч {m}м назад"
    return f"{m}м назад"


# ──────────────────────────────────────────────
# Существующие команды
# ──────────────────────────────────────────────

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


@router.message(Command("sync"))
async def admin_sync(message: Message):
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
        f"/sync — обновить из Notion\n"
        f"/sync --full — полная переиндексация",
        parse_mode="HTML",
    )


@router.message(Command("setpro"))
async def admin_set_pro(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /setpro <telegram_user_id>")
        return
    target_id = int(parts[1])
    async with async_session() as session:
        await session.execute(update(User).where(User.telegram_id == target_id).values(is_pro=True))
        await session.commit()
    await message.answer(f"✅ Пользователю {target_id} выдана Pro подписка")


# ──────────────────────────────────────────────
# Новые команды — Этап 3
# ──────────────────────────────────────────────

@router.message(Command("branches"))
async def admin_branches(message: Message):
    """/branches — статус всех веток."""
    if not is_admin(message.from_user.id):
        return

    lines = ["📡 <b>Статус веток</b>\n"]
    for branch in BRANCHES:
        persona = BRANCH_PERSONAS.get(branch, {})
        emoji = persona.get("emoji", "•")
        name = BRANCH_META[branch]["name"]
        last = await get_branch_last_post(branch)
        lines.append(f"{emoji} <b>{name}</b> — {_ago(last)}")

    langs_cfg = settings.BRANCH_LANGUAGES
    if langs_cfg:
        lines.append("\n🌐 <b>Языки:</b>")
        for branch, langs in langs_cfg.items():
            lines.append(f"  • {branch}: {', '.join(langs)}")

    lines.append(
        "\n<i>/publish health — опубликовать health-пост\n"
        "/publish health en — на английском</i>"
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("publish"))
async def admin_publish(message: Message):
    """/publish <branch> [lang] — ручная публикация поста.

    Примеры:
      /publish health
      /publish tech en
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            f"Использование: <code>/publish &lt;branch&gt; [lang]</code>\n\n"
            f"Ветки: {' | '.join(BRANCHES)}\n"
            f"Языки: ru | en | uk | pl | de | es | fr | tr",
            parse_mode="HTML",
        )
        return

    branch = parts[1].lower()
    if branch not in BRANCHES:
        await message.answer(f"❌ Неизвестная ветка: {branch}\nДоступные: {', '.join(BRANCHES)}")
        return

    lang = parts[2].lower() if len(parts) > 2 else "ru"
    emoji = BRANCH_PERSONAS.get(branch, {}).get("emoji", "📝")

    msg = await message.answer(f"⏳ Генерирую {emoji} {branch}-пост [{lang}]...")
    try:
        text = await generate_branch_post(branch, language=lang)

        preview = text[:800] + ("..." if len(text) > 800 else "")
        await msg.edit_text(
            f"📝 <b>Превью [{branch} / {lang}]:</b>\n\n{preview}\n\n<i>Отправляю в канал...</i>",
            parse_mode="HTML",
        )

        # Определяем канал
        channels = settings.BRANCH_CHANNELS.get(branch, {})
        channel = channels.get(lang)
        if not channel:
            attr = f"CHANNEL_{branch.upper()}"
            channel = getattr(settings, attr, "") or settings.CHANNEL_ID

        if channel:
            await message.bot.send_message(channel, text, parse_mode="HTML")
            await message.answer(f"✅ Опубликовано → {channel}")

            from bot.services.database import log_published_post
            await log_published_post(
                branch=branch, platform="telegram", text=text,
                language=lang, title_preview=text[:100],
            )
        else:
            await message.answer("⚠️ Канал не настроен. Проверь BRANCH_CHANNELS в .env")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("analytics"))
async def admin_analytics(message: Message):
    """/analytics [days] — статистика публикаций."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 7
    data = await get_analytics(days=days)

    platform_lines = "\n".join(
        f"  • {p}: <b>{c}</b>"
        for p, c in sorted(data["by_platform"].items(), key=lambda x: -x[1])
    ) or "  нет данных"

    branch_lines = "\n".join(
        f"  • {b}: <b>{c}</b>"
        for b, c in sorted(data["by_branch"].items(), key=lambda x: -x[1])
    ) or "  нет данных"

    await message.answer(
        f"📈 <b>Аналитика за {days} дней</b>\n\n"
        f"📦 Всего постов: <b>{data['total']}</b>\n\n"
        f"<b>По платформам:</b>\n{platform_lines}\n\n"
        f"<b>По веткам:</b>\n{branch_lines}",
        parse_mode="HTML",
    )


@router.message(Command("sources"))
async def admin_sources(message: Message):
    """/sources [category] — список RSS-источников."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    category = parts[1].lower() if len(parts) > 1 else None
    sources = await get_active_sources(category)

    if not sources:
        hint = f" для '{category}'" if category else ""
        await message.answer(
            f"Нет активных источников{hint}.\n\n"
            f"Добавить: <code>/addsource &lt;url&gt; &lt;category&gt;</code>",
            parse_mode="HTML",
        )
        return

    header = f"📰 <b>RSS-источники</b>{' [' + category + ']' if category else ''}\n"
    lines = [header]
    for s in sources:
        lines.append(f"<b>#{s.id}</b> [{s.category}] {s.url[:55]}\n   Запрос: {_ago(s.last_fetched)}")

    lines.append("\n<code>/addsource &lt;url&gt; &lt;cat&gt;</code> — добавить\n<code>/delsource &lt;id&gt;</code> — отключить")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("addsource"))
async def admin_add_source(message: Message):
    """/addsource <url> <category> — добавить RSS-источник."""
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            f"Использование: <code>/addsource &lt;url&gt; &lt;category&gt;</code>\n"
            f"Категории: {', '.join(BRANCHES)}",
            parse_mode="HTML",
        )
        return
    url, category = parts[1], parts[2].lower()
    if category not in BRANCHES:
        await message.answer(f"❌ Неизвестная категория: {category}")
        return
    try:
        source = await add_news_source(url=url, category=category)
        await message.answer(f"✅ Источник добавлен (#{source.id})\n{url}")
    except Exception as e:
        await message.answer(f"❌ Ошибка (возможно, URL уже есть): {e}")


@router.message(Command("delsource"))
async def admin_del_source(message: Message):
    """/delsource <id> — деактивировать RSS-источник."""
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delsource <id>")
        return
    await toggle_news_source(int(parts[1]), is_active=False)
    await message.answer(f"✅ Источник #{parts[1]} деактивирован")


@router.message(Command("yscript"))
async def admin_youtube_script(message: Message):
    """/yscript <branch> [shorts|long] [lang] [topic...]

    Примеры:
      /yscript health shorts ru
      /yscript tech long en Quantum computing for beginners
      /yscript finance long
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=4)
    if len(parts) < 2:
        await message.answer(
            f"Использование: <code>/yscript &lt;branch&gt; [shorts|long] [lang] [topic]</code>\n\n"
            f"Ветки: {' | '.join(BRANCHES)}\n"
            f"Формат: shorts (60 сек) | long (10-15 мин, по умолчанию)\n"
            f"Языки: ru | en | uk | pl | de | es | fr | tr",
            parse_mode="HTML",
        )
        return

    branch = parts[1].lower()
    if branch not in BRANCHES:
        await message.answer(f"❌ Неизвестная ветка: {branch}\nДоступные: {', '.join(BRANCHES)}")
        return

    fmt = "long"
    lang = "ru"
    topic: str | None = None

    remaining = parts[2:]
    if remaining and remaining[0].lower() in ("shorts", "long"):
        fmt = remaining[0].lower()
        remaining = remaining[1:]
    if remaining and len(remaining[0]) <= 3 and remaining[0].isalpha():
        lang = remaining[0].lower()
        remaining = remaining[1:]
    if remaining:
        topic = " ".join(remaining)

    from bot.services.script_generator import generate_shorts_script, generate_video_script
    emoji = BRANCH_PERSONAS.get(branch, {}).get("emoji", "🎬")
    fmt_label = "Shorts (60 сек)" if fmt == "shorts" else "Видео (10-15 мин)"

    msg = await message.answer(
        f"⏳ Генерирую {emoji} {fmt_label} сценарий [{branch} / {lang}]..."
    )
    try:
        if fmt == "shorts":
            script = await generate_shorts_script(branch=branch, topic=topic, language=lang)
            text = script.as_text()
        else:
            script = await generate_video_script(branch=branch, topic=topic, language=lang)
            text = script.as_text()

        # Telegram: max 4096 символов — разбиваем если нужно
        if len(text) <= 4000:
            await msg.edit_text(f"🎬 <b>Сценарий готов</b>\n\n<pre>{text}</pre>", parse_mode="HTML")
        else:
            await msg.edit_text("🎬 <b>Сценарий готов</b> (длинный, отправляю частями)")
            for chunk_start in range(0, len(text), 3800):
                chunk = text[chunk_start:chunk_start + 3800]
                await message.answer(f"<pre>{chunk}</pre>", parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации сценария: {e}")


@router.message(Command("ystats"))
async def admin_youtube_stats(message: Message):
    """/ystats — статистика YouTube-канала."""
    if not is_admin(message.from_user.id):
        return
    from bot.services.youtube_publisher import get_channel_stats
    msg = await message.answer("⏳ Получаю статистику YouTube...")
    stats = await get_channel_stats()
    if "error" in stats:
        await msg.edit_text(f"❌ YouTube: {stats['error']}")
        return
    await msg.edit_text(
        f"▶️ <b>YouTube-канал</b>\n\n"
        f"📺 Название: <b>{stats['title']}</b>\n"
        f"👥 Подписчиков: <b>{stats['subscribers']:,}</b>\n"
        f"👁 Просмотров: <b>{stats['views']:,}</b>\n"
        f"🎬 Видео: <b>{stats['videos']}</b>",
        parse_mode="HTML",
    )


@router.message(Command("insight"))
async def admin_insight(message: Message):
    if not is_admin(message.from_user.id):
        return
    await task_daily_insight(message.bot)
    await message.answer("✅ Инсайт опубликован!")


@router.message(Command("adminhelp"))
async def admin_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 <b>Admin-команды</b>\n\n"
        "<b>Контент:</b>\n"
        "/publish &lt;branch&gt; [lang] — опубликовать пост\n"
        "/insight — инсайт дня прямо сейчас\n\n"
        "<b>Мониторинг:</b>\n"
        "/branches — статус всех веток\n"
        "/analytics [days] — статистика постов\n"
        "/stats — пользователи и доход\n\n"
        "<b>RSS-источники:</b>\n"
        "/sources [cat] — список\n"
        "/addsource &lt;url&gt; &lt;cat&gt; — добавить\n"
        "/delsource &lt;id&gt; — отключить\n\n"
        "<b>База знаний:</b>\n"
        "/sync — обновить из Notion\n"
        "/kbstats — статистика\n\n"
        "<b>YouTube:</b>\n"
        "/yscript &lt;branch&gt; [shorts|long] [lang] [topic] — сценарий\n"
        "/ystats — статистика канала\n\n"
        "<b>Пользователи:</b>\n"
        "/setpro &lt;user_id&gt; — выдать Pro",
        parse_mode="HTML",
    )
