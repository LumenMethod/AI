"""Генератор контента по тематическим веткам "Человек 2035"."""
import logging

import anthropic

from config.settings import settings
from bot.services.news_aggregator import NewsItem

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Описание каждой ветки для промптов
BRANCH_META = {
    "health": {
        "emoji": "🧠",
        "name": "Здоровье 2035",
        "focus": "здоровые привычки, спорт, питание, сон, ментальное здоровье, биохакинг",
        "hashtags": "#здоровье2035 #биохакинг #longevity #здоровыйобраз #человек2035",
    },
    "finance": {
        "emoji": "💰",
        "name": "Финансы 2035",
        "focus": "личные финансы, инвестиции, крипто, новые профессии, экономика будущего",
        "hashtags": "#финансы2035 #инвестиции #крипто #пассивныйдоход #человек2035",
    },
    "tech": {
        "emoji": "🤖",
        "name": "Технологии 2035",
        "focus": "AI, машинное обучение, биотех, нейроинтерфейсы, квантовые вычисления",
        "hashtags": "#технологии2035 #AI #инновации #будущее #человек2035",
    },
    "news": {
        "emoji": "📰",
        "name": "Новости 2035",
        "focus": "мировые события через призму будущего, тренды, дайджест",
        "hashtags": "#новости2035 #дайджест #тренды #мир #человек2035",
    },
    "edu": {
        "emoji": "🎓",
        "name": "Образование 2035",
        "focus": "навыки будущего, онлайн-обучение, книги, soft skills, когнитивное усиление",
        "hashtags": "#образование2035 #навыки #обучение #книги #человек2035",
    },
}

_SYSTEM = (
    "Ты — SMM-редактор и футуролог канала «Человек 2035». "
    "Пишешь по-русски. Стиль: живой, вдохновляющий, с конкретными фактами. "
    "Никогда не пиши пустые обещания — только практическую ценность. "
    "Используй эмодзи умеренно. Избегай воды и клише."
)


async def generate_branch_post(branch: str, news_item: NewsItem | None = None) -> str:
    """
    Генерирует Telegram-пост для указанной ветки.
    Если передан news_item — строит пост на основе новости.
    """
    meta = BRANCH_META.get(branch, BRANCH_META["tech"])

    if news_item:
        context = (
            f"Используй эту новость как основу:\n"
            f"Заголовок: {news_item.title}\n"
            f"Краткое содержание: {news_item.summary}\n"
            f"Ссылка: {news_item.link}\n\n"
        )
    else:
        context = ""

    prompt = (
        f"{context}"
        f"Создай пост для Telegram-канала «{meta['name']}» {meta['emoji']}.\n\n"
        f"Тематика ветки: {meta['focus']}.\n\n"
        f"Структура поста:\n"
        f"1. Цепляющий заголовок (1 строка, с эмодзи)\n"
        f"2. Основной текст (3-4 абзаца, 600-900 символов)\n"
        f"3. Практический совет — что сделать сегодня\n"
        f"4. Хештеги: {meta['hashtags']}\n\n"
        f"Формат: HTML-разметка Telegram (жирный — <b>, курсив — <i>). "
        f"Максимум 1200 символов без хештегов."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=900,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_morning_digest(all_news: dict[str, list[NewsItem]]) -> str:
    """
    Генерирует утренний дайджест для главного канала на основе
    новостей по всем веткам.
    """
    news_lines = []
    for branch, items in all_news.items():
        meta = BRANCH_META.get(branch, {})
        emoji = meta.get("emoji", "•")
        name = meta.get("name", branch)
        for item in items[:1]:  # по одной новости от каждой ветки
            news_lines.append(f"{emoji} <b>{name}</b>: {item.title}")

    news_block = "\n".join(news_lines) if news_lines else "Свежих новостей пока нет."

    prompt = (
        f"Создай утренний дайджест для Telegram-канала «Человек 2035» 🌅.\n\n"
        f"Сегодняшние топ-события по веткам:\n{news_block}\n\n"
        f"Структура:\n"
        f"1. Приветствие + дата\n"
        f"2. Краткий обзор по каждой теме (1-2 предложения)\n"
        f"3. Главный инсайт дня (одна мысль, которая зарядит)\n"
        f"4. Призыв к действию\n"
        f"5. #дайджест2035 #человек2035\n\n"
        f"Формат: HTML Telegram. Максимум 1500 символов."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_evening_digest(posted_today: list[str]) -> str:
    """
    Генерирует вечерний дайджест с перечислением лучших постов дня.
    `posted_today` — список заголовков/тем постов, вышедших за день.
    """
    topics_block = "\n".join(f"• {t}" for t in posted_today) if posted_today else "Контент дня."

    prompt = (
        f"Создай вечерний дайджест для Telegram-канала «Человек 2035» 🌙.\n\n"
        f"Темы, которые мы разобрали сегодня:\n{topics_block}\n\n"
        f"Структура:\n"
        f"1. Вечернее приветствие\n"
        f"2. Краткое резюме дня (что было важного)\n"
        f"3. Вопрос для рефлексии — один вопрос, над которым стоит подумать перед сном\n"
        f"4. #вечер2035 #человек2035\n\n"
        f"Формат: HTML Telegram. Максимум 800 символов."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=600,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
