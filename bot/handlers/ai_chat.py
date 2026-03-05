from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.database import check_and_increment_requests, get_user_stats
from bot.services.claude_ai import ask_claude, generate_daily_insight
from config.settings import settings

router = Router()


class AskAI(StatesGroup):
    waiting_for_question = State()


def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Ещё вопрос", callback_data="ask_ai")],
        [InlineKeyboardButton(text="◀️ Меню", callback_data="back_menu")],
    ])


@router.callback_query(F.data == "ask_ai")
async def ask_ai_start(callback: CallbackQuery, state: FSMContext):
    stats = await get_user_stats(callback.from_user.id)
    is_unlimited = stats.get("is_pro") or stats.get("is_expert")
    daily = stats.get("daily_requests", 0)

    if not is_unlimited and daily >= settings.FREE_DAILY_LIMIT:
        await callback.message.edit_text(
            f"⚡️ <b>Лимит запросов исчерпан</b>\n\n"
            f"Сегодня ты использовал все {settings.FREE_DAILY_LIMIT} бесплатных запроса.\n\n"
            "🔥 <b>Перейди на Pro</b> — безлимитные запросы всего за "
            f"{settings.PRO_MONTHLY_PRICE}₽/мес",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"⭐️ Получить Pro", callback_data="go_pro")],
                [InlineKeyboardButton(text="◀️ Меню", callback_data="back_menu")],
            ]),
        )
        await callback.answer()
        return

    remaining = "∞" if is_unlimited else f"{settings.FREE_DAILY_LIMIT - daily}"
    await callback.message.edit_text(
        f"🔮 <b>Спроси AI о будущем</b>\n\n"
        f"Осталось запросов сегодня: <b>{remaining}</b>\n\n"
        "Примеры вопросов:\n"
        "• Как AI изменит мою профессию к 2035?\n"
        "• Что такое биохакинг и с чего начать?\n"
        "• Как подготовиться к финансовому будущему?\n\n"
        "✍️ <b>Напиши свой вопрос:</b>",
        parse_mode="HTML",
    )
    await state.set_state(AskAI.waiting_for_question)
    await callback.answer()


@router.message(AskAI.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    await state.clear()

    allowed = await check_and_increment_requests(message.from_user.id)
    if not allowed:
        await message.answer(
            f"⚡️ Лимит {settings.FREE_DAILY_LIMIT} запроса в день исчерпан.\n"
            f"Перейди на Pro за {settings.PRO_MONTHLY_PRICE}₽/мес для безлимита.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐️ Pro подписка", callback_data="go_pro")],
            ]),
        )
        return

    thinking_msg = await message.answer("🤔 <i>Думаю...</i>", parse_mode="HTML")

    stats = await get_user_stats(message.from_user.id)
    answer = await ask_claude(message.text, user_interest=stats.get("interest"))

    await thinking_msg.delete()
    await message.answer(
        f"🔮 <b>Ответ AI</b>\n\n{answer}",
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


@router.callback_query(F.data == "daily_insight")
async def show_daily_insight(callback: CallbackQuery):
    await callback.message.edit_text("⏳ <i>Генерирую инсайт...</i>", parse_mode="HTML")

    insight = await generate_daily_insight()

    await callback.message.edit_text(
        insight,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔮 Спросить AI", callback_data="ask_ai")],
            [InlineKeyboardButton(text="◀️ Меню", callback_data="back_menu")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "my_roadmap")
async def my_roadmap(callback: CallbackQuery, state: FSMContext):
    stats = await get_user_stats(callback.from_user.id)

    if not stats.get("is_pro") and not stats.get("is_expert"):
        await callback.message.edit_text(
            "🗺 <b>Личный план до 2035</b>\n\n"
            "Эта функция доступна для Pro и Expert подписчиков.\n\n"
            "AI составит персональную дорожную карту:\n"
            "• Какие навыки развить\n"
            "• Какие технологии освоить\n"
            "• Как защитить своё финансовое будущее\n"
            "• Как оставаться здоровым до 2035 и дальше",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"⭐️ Получить Pro — {settings.PRO_MONTHLY_PRICE}₽/мес", callback_data="go_pro")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_menu")],
            ]),
        )
        await callback.answer()
        return

    await state.set_state(AskAI.waiting_for_question)
    await callback.message.edit_text(
        "🗺 <b>Создаю твой план до 2035</b>\n\n"
        "Расскажи о себе:\n"
        "• Твой возраст и профессия\n"
        "• Главная цель на следующие 10 лет\n"
        "• Что тебя беспокоит в будущем?\n\n"
        "✍️ <b>Напиши, и я создам персональный план:</b>",
        parse_mode="HTML",
    )
    await callback.answer()
