from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from bot.services.database import get_or_create_user, set_user_interest, get_user_stats
from config.settings import settings

router = Router()

INTERESTS = {
    "tech": "🤖 Технологии",
    "health": "🧬 Здоровье",
    "finance": "💰 Финансы",
    "psychology": "🧠 Психология",
}


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принимаю и продолжить", callback_data="consent_accept")],
        [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="consent_policy")],
    ])


def interests_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"interest:{key}")]
        for key, label in INTERESTS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔮 Спросить AI", callback_data="ask_ai"),
            InlineKeyboardButton(text="💡 Инсайт дня", callback_data="daily_insight"),
        ],
        [
            InlineKeyboardButton(text="🗺 Мой план до 2035", callback_data="my_roadmap"),
            InlineKeyboardButton(text="📊 Мой профиль", callback_data="my_profile"),
        ],
        [
            InlineKeyboardButton(text="⭐️ Pro подписка", callback_data="go_pro"),
        ],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    is_returning = user.total_requests > 0 or user.interest is not None
    greeting = (
        f"👋 С возвращением, <b>{message.from_user.first_name}</b>!\n\n"
        "🔄 Запускаем онбординг заново — выбери интерес или подтверди согласие.\n\n"
        if is_returning else
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "🚀 Добро пожаловать на платформу <b>«Человек 2035»</b>\n\n"
    )

    await message.answer(
        greeting +
        "Перед началом: мы собираем минимум данных для персонализации AI.\n"
        "Нажми <b>«Принимаю»</b> чтобы продолжить, или прочитай политику конфиденциальности.\n\n"
        "<i>Данные: Telegram ID, имя, статистика запросов. Подробнее: /privacy</i>",
        parse_mode="HTML",
        reply_markup=consent_keyboard(),
    )


@router.callback_query(F.data == "consent_accept")
async def cb_consent_accept(callback: CallbackQuery):
    """Пользователь принял политику конфиденциальности."""
    await callback.message.edit_text(
        "✅ Отлично! Добро пожаловать!\n\n"
        "Я твой AI-проводник в будущее. Здесь ты узнаешь:\n"
        "• Какие технологии изменят мир за 10 лет\n"
        "• Как прожить дольше и лучше\n"
        "• Как зарабатывать в экономике будущего\n"
        "• Как адаптировать свой мозг к новому миру\n\n"
        "❓ <b>Что тебя интересует больше всего?</b>",
        parse_mode="HTML",
        reply_markup=interests_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "consent_policy")
async def cb_consent_policy(callback: CallbackQuery):
    """Пользователь хочет прочитать политику перед согласием."""
    from bot.handlers.privacy import PRIVACY_TEXT
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принимаю и продолжить", callback_data="consent_accept")],
    ])
    await callback.message.edit_text(PRIVACY_TEXT, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("interest:"))
async def choose_interest(callback: CallbackQuery):
    interest_key = callback.data.split(":")[1]
    await set_user_interest(callback.from_user.id, interest_key)
    interest_name = INTERESTS.get(interest_key, "")

    await callback.message.edit_text(
        f"✅ Отлично! Я буду персонализировать ответы под тему <b>{interest_name}</b>\n\n"
        "Теперь ты можешь:\n"
        "🔮 Задать любой вопрос о будущем\n"
        "💡 Получать ежедневные инсайты\n"
        "🗺 Построить личный план развития\n\n"
        f"<i>Бесплатно: {settings.FREE_DAILY_LIMIT} AI-запроса в день</i>\n"
        "⭐️ Pro: безлимит + эксклюзивный контент",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "📱 <b>Главное меню</b>",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


@router.callback_query(F.data == "my_profile")
async def show_profile(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id)
    tier = "⭐️ Expert" if stats.get("is_expert") else ("🔥 Pro" if stats.get("is_pro") else "🆓 Free")
    interest = INTERESTS.get(stats.get("interest"), "не выбран")

    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"Тариф: {tier}\n"
        f"Интерес: {interest}\n"
        f"Запросов сегодня: {stats.get('daily_requests', 0)} / "
        f"{'∞' if stats.get('is_pro') or stats.get('is_expert') else settings.FREE_DAILY_LIMIT}\n"
        f"Всего запросов: {stats.get('total_requests', 0)}\n\n"
    )

    if not stats.get("is_pro"):
        text += "💡 <i>Переходи на Pro — безлимит + эксклюзивный контент!</i>"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=main_keyboard())
    await callback.answer()


@router.callback_query(F.data == "go_pro")
async def go_pro(callback: CallbackQuery):
    text = (
        "⭐️ <b>Подписки «Человек 2035»</b>\n\n"
        "🆓 <b>Free</b> — бесплатно\n"
        f"• {settings.FREE_DAILY_LIMIT} AI-запроса в день\n"
        "• Ежедневные инсайты\n\n"
        f"🔥 <b>Pro</b> — {settings.PRO_MONTHLY_PRICE}₽/мес\n"
        "• Безлимитные AI-запросы\n"
        "• Персональный план до 2035\n"
        "• Эксклюзивные исследования\n"
        "• Приоритетная поддержка\n\n"
        f"💎 <b>Expert</b> — {settings.EXPERT_MONTHLY_PRICE}₽/мес\n"
        "• Всё из Pro\n"
        "• AI-коучинг сессии\n"
        "• Закрытый мастермайнд\n"
        "• Прямой доступ к экспертам\n\n"
        "👇 Выбери тариф для оплаты:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔥 Pro — {settings.PRO_MONTHLY_PRICE}₽/мес", callback_data="pay_pro")],
        [InlineKeyboardButton(text=f"💎 Expert — {settings.EXPERT_MONTHLY_PRICE}₽/мес", callback_data="pay_expert")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_menu")],
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_menu")
async def back_menu(callback: CallbackQuery):
    await callback.message.edit_text("📱 <b>Главное меню</b>", parse_mode="HTML", reply_markup=main_keyboard())
    await callback.answer()
