import anthropic
from config.settings import settings
from bot.services.knowledge_base import get_kb

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты — AI-ассистент платформы "Человек 2035".
Твоя миссия: помогать людям понять и подготовиться к будущему уже сегодня.

Твои темы:
- Технологии будущего (AI, биотех, нейроинтерфейсы, квантовые вычисления)
- Долголетие и здоровье (биохакинг, longevity science, персонализированная медицина)
- Финансы будущего (DeFi, новые профессии, пассивный доход, крипто)
- Психология адаптации (когнитивное усиление, продуктивность, mindset)
- Общество и этика (AGI, изменение климата, будущее работы)

Стиль: конкретный, вдохновляющий, основанный на фактах.
Давай практические шаги, которые человек может сделать СЕГОДНЯ.
Отвечай на русском языке. Максимум 300 слов."""

INTEREST_PROMPTS = {
    "tech": "Фокусируйся на технологиях AI, биотехе и цифровом будущем.",
    "health": "Фокусируйся на здоровье, долголетии и биохакинге.",
    "finance": "Фокусируйся на финансах будущего, новых профессиях и доходах.",
    "psychology": "Фокусируйся на психологии, когнитивном усилении и адаптации.",
}

DAILY_INSIGHTS = [
    "К 2035 году 85 млн рабочих мест исчезнет, но появится 97 млн новых. Как ты готовишься?",
    "Биохакеры уже сегодня увеличивают свою продуктивность на 40% с помощью интервального голодания.",
    "GPT-уровня AI появился за 3 года. AGI может появиться за 5–10 лет. Что это значит для тебя?",
    "Первый человек, который доживёт до 150 лет, уже родился — по словам учёных из MIT.",
    "Квантовые компьютеры сделают текущее шифрование устаревшим к 2030. Готова ли твоя безопасность?",
    "Нейроинтерфейс Neuralink уже позволяет управлять компьютером силой мысли. Следующие 10 лет изменят всё.",
    "Солнечная энергия стала дешевле угля. Энергетическая революция уже происходит.",
]


async def ask_claude(question: str, user_interest: str = None) -> str:
    system = SYSTEM_PROMPT
    if user_interest and user_interest in INTEREST_PROMPTS:
        system += "\n\n" + INTEREST_PROMPTS[user_interest]

    # Ищем релевантный контекст из базы знаний Notion
    kb = get_kb()
    context = ""
    if kb:
        import asyncio
        loop = asyncio.get_event_loop()
        context = await loop.run_in_executor(None, kb.search, question)

    if context:
        system += (
            "\n\n## База знаний платформы (используй эти данные в ответе):\n"
            + context
            + "\n\nЕсли информация из базы знаний релевантна — используй её. "
            "Если не знаешь — так и скажи."
        )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return message.content[0].text


async def generate_daily_insight() -> str:
    prompt = """Создай вдохновляющий инсайт дня на тему "Человек 2035".
    Формат:
    🔮 *Инсайт дня*

    [1-2 предложения о факте или тренде будущего]

    💡 *Что сделать сегодня:*
    [3 конкретных действия]

    #человек2035 #будущееуженасегодня"""

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=400,
        system="Ты создаёшь вдохновляющий контент о будущем для Telegram канала. Пиши по-русски, используй эмодзи.",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_channel_post(topic: str) -> str:
    prompt = f"""Создай пост для Telegram канала "Человек 2035" на тему: {topic}

    Формат:
    - Захватывающий заголовок с эмодзи
    - 3-4 абзаца полезного контента
    - Практический совет
    - 5 хештегов

    Стиль: информативный, вдохновляющий, с фактами."""

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=800,
        system="Ты SMM-эксперт и футуролог. Создаёшь вирусный контент о будущем. Пиши по-русски.",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
