"""Генератор контента по тематическим веткам "Человек 2035".

Поддержка аватаров (персон) и мультиязычности.
Каждая ветка имеет своего персонажа-автора и список языков для публикации.
"""
import logging

import anthropic

from config.settings import settings
from bot.services.news_aggregator import NewsItem

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# ──────────────────────────────────────────────
# Аватары (персоны) веток
# ──────────────────────────────────────────────

BRANCH_PERSONAS: dict[str, dict] = {
    "health": {
        "name": "Dr. Anya",
        "role": "врач-биохакер, нутрициолог и эксперт по долголетию",
        "style": (
            "Научно обоснованный, заботливый, мотивирующий. "
            "Говорит как лучший друг-врач — без страшилок, только факты и действия. "
            "Ценит доказательную медицину, но открыта к новому."
        ),
        "emoji": "🧬",
        "signature": "— Dr. Anya 🧬",
    },
    "finance": {
        "name": "Max Capital",
        "role": "финансовый аналитик, инвестор и исследователь экономики будущего",
        "style": (
            "Конкретный, без воды, всегда с цифрами и примерами. "
            "Говорит как уверенный инсайдер рынка. "
            "Не обещает лёгких денег — учит мыслить системно."
        ),
        "emoji": "📊",
        "signature": "— Max Capital 📊",
    },
    "tech": {
        "name": "Nova",
        "role": "AI-исследователь, технофутурист и инженер по нейроинтерфейсам",
        "style": (
            "Увлечённый, живёт на грани науки и фантастики, "
            "но всегда с реальными примерами и ссылками на факты. "
            "Заразительный энтузиазм — читатель чувствует, что будущее уже здесь."
        ),
        "emoji": "🤖",
        "signature": "— Nova 🤖",
    },
    "news": {
        "name": "Alex Lens",
        "role": "журналист-аналитик мировых событий и трендвотчер",
        "style": (
            "Объективный, глубокий, умеет находить неочевидные связи между событиями. "
            "Не паникует и не хайпует — показывает большую картину. "
            "Читатель выходит с ощущением, что понял мир лучше."
        ),
        "emoji": "🌍",
        "signature": "— Alex Lens 🌍",
    },
    "edu": {
        "name": "Professor Sam",
        "role": "педагог, ментор и коуч по навыкам будущего",
        "style": (
            "Вдохновляющий, структурированный, с практическими заданиями. "
            "Каждый пост — это мини-урок с конкретным takeaway. "
            "Верит, что учиться можно всю жизнь и это меняет всё."
        ),
        "emoji": "🎓",
        "signature": "— Prof. Sam 🎓",
    },
}

# ──────────────────────────────────────────────
# Описание веток
# ──────────────────────────────────────────────

BRANCH_META: dict[str, dict] = {
    "health": {
        "name": "Здоровье 2035",
        "focus": "здоровые привычки, спорт, питание, сон, ментальное здоровье, биохакинг, longevity",
        "hashtags": "#health2035 #biohacking #longevity #wellness #human2035",
    },
    "finance": {
        "name": "Финансы 2035",
        "focus": "личные финансы, инвестиции, крипто, новые профессии, экономика будущего",
        "hashtags": "#finance2035 #investing #crypto #passiveincome #human2035",
    },
    "tech": {
        "name": "Технологии 2035",
        "focus": "AI, машинное обучение, биотех, нейроинтерфейсы, квантовые вычисления",
        "hashtags": "#tech2035 #AI #innovation #future #human2035",
    },
    "news": {
        "name": "Новости 2035",
        "focus": "мировые события через призму будущего, тренды, аналитика",
        "hashtags": "#news2035 #digest #trends #world #human2035",
    },
    "edu": {
        "name": "Образование 2035",
        "focus": "навыки будущего, онлайн-обучение, книги, soft skills, когнитивное усиление",
        "hashtags": "#edu2035 #skills #learning #books #human2035",
    },
}

# ──────────────────────────────────────────────
# Поддерживаемые языки
# ──────────────────────────────────────────────

SUPPORTED_LANGUAGES: dict[str, str] = {
    "ru": "русском языке",
    "en": "English",
    "uk": "українській мові",
    "pl": "języku polskim",
    "de": "Deutsch",
    "es": "español",
    "fr": "français",
    "tr": "Türkçe",
    "ar": "اللغة العربية",
    "zh": "中文",
}

# Языки с написанием справа-налево (для заметок в промптах)
_RTL_LANGS = {"ar"}


def _build_system_prompt(branch: str, language: str) -> str:
    """Строит системный промпт с персоной и языковой инструкцией."""
    persona = BRANCH_PERSONAS.get(branch, BRANCH_PERSONAS["tech"])
    lang_name = SUPPORTED_LANGUAGES.get(language, language)

    rtl_note = " Текст пишется справа налево." if language in _RTL_LANGS else ""

    return (
        f"Ты — {persona['name']}, {persona['role']}.\n"
        f"Твой стиль: {persona['style']}\n"
        f"Подписывай каждый пост: {persona['signature']}\n\n"
        f"ВАЖНО: Пиши ТОЛЬКО на {lang_name}.{rtl_note} "
        f"Весь текст поста — на этом языке. "
        f"Используй эмодзи умеренно. Избегай воды и клише. "
        f"Только практическая ценность."
    )


# ──────────────────────────────────────────────
# Генераторы постов
# ──────────────────────────────────────────────

async def generate_branch_post(
    branch: str,
    news_item: NewsItem | None = None,
    language: str = "ru",
) -> str:
    """
    Генерирует Telegram-пост для ветки на указанном языке.
    Если передан news_item — строит пост на основе новости.
    """
    meta = BRANCH_META.get(branch, BRANCH_META["tech"])
    system = _build_system_prompt(branch, language)
    lang_name = SUPPORTED_LANGUAGES.get(language, language)

    news_block = ""
    if news_item:
        news_block = (
            f"Base this post on the following news item:\n"
            f"Title: {news_item.title}\n"
            f"Summary: {news_item.summary}\n"
            f"Link: {news_item.link}\n\n"
        )

    prompt = (
        f"{news_block}"
        f"Create a Telegram post for the '{meta['name']}' channel.\n"
        f"Topic area: {meta['focus']}.\n\n"
        f"Post structure:\n"
        f"1. Catchy headline (1 line, with emoji)\n"
        f"2. Main content (3-4 paragraphs, 600-900 characters)\n"
        f"3. Practical tip — what to do today\n"
        f"4. Hashtags: {meta['hashtags']}\n"
        f"5. Your signature\n\n"
        f"Format: Telegram HTML markup (<b>bold</b>, <i>italic</i>).\n"
        f"Write entirely in {lang_name}. Max 1200 characters (excluding hashtags)."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=900,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_morning_digest(
    all_news: dict[str, list[NewsItem]],
    language: str = "ru",
) -> str:
    """Утренний дайджест для главного канала на указанном языке."""
    lang_name = SUPPORTED_LANGUAGES.get(language, language)

    news_lines = []
    for branch, items in all_news.items():
        meta = BRANCH_META.get(branch, {})
        persona = BRANCH_PERSONAS.get(branch, {})
        emoji = persona.get("emoji", "•")
        name = meta.get("name", branch)
        for item in items[:1]:
            news_lines.append(f"{emoji} <b>{name}</b>: {item.title}")

    news_block = "\n".join(news_lines) if news_lines else "No fresh news yet."

    prompt = (
        f"Create a morning digest for the 'Human 2035' Telegram channel 🌅.\n\n"
        f"Today's top stories by category:\n{news_block}\n\n"
        f"Structure:\n"
        f"1. Greeting + date\n"
        f"2. Brief overview of each topic (1-2 sentences)\n"
        f"3. Main insight of the day (one energising thought)\n"
        f"4. Call to action\n"
        f"5. #digest2035 #human2035\n\n"
        f"Format: Telegram HTML. Max 1500 characters.\n"
        f"Write entirely in {lang_name}."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1000,
        system=f"You are a morning news host for the Human 2035 project. Write in {lang_name}.",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_evening_digest(
    posted_today: list[str],
    language: str = "ru",
) -> str:
    """Вечерний дайджест на указанном языке."""
    lang_name = SUPPORTED_LANGUAGES.get(language, language)
    topics_block = "\n".join(f"• {t}" for t in posted_today) if posted_today else "Today's content."

    prompt = (
        f"Create an evening digest for the 'Human 2035' Telegram channel 🌙.\n\n"
        f"Topics covered today:\n{topics_block}\n\n"
        f"Structure:\n"
        f"1. Evening greeting\n"
        f"2. Brief summary of the day\n"
        f"3. Reflection question — one thought to ponder before sleep\n"
        f"4. #evening2035 #human2035\n\n"
        f"Format: Telegram HTML. Max 800 characters.\n"
        f"Write entirely in {lang_name}."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=600,
        system=f"You are an evening host for the Human 2035 project. Write in {lang_name}.",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
