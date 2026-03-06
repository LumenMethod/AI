"""Политика конфиденциальности и права пользователя.

Реализует требования:
  • GDPR (Regulation EU 2016/679) — право на доступ, исправление, удаление
  • ФЗ-152 «О персональных данных» (Россия)

Команды для пользователей:
  /privacy    — политика конфиденциальности и список собираемых данных
  /mydata     — показать все мои данные
  /deletedata — запрос на удаление персональных данных
"""
import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from bot.services.database import get_full_user_data, delete_user_data

router = Router()

# ──────────────────────────────────────────────
# Текст политики
# ──────────────────────────────────────────────

PRIVACY_TEXT = """🔒 <b>Политика конфиденциальности</b>
«Человек 2035» | @human2035bot

<b>Какие данные мы собираем:</b>
• Telegram ID, имя и @username (из профиля Telegram)
• Тематический интерес (выбираешь сам при регистрации)
• Статистику использования (кол-во запросов к AI)
• Тариф подписки (Free / Pro / Expert)
• Демографический профиль (если заполняешь добровольно)

<b>Зачем используем:</b>
• Персонализация ответов AI
• Подсчёт лимитов бесплатных запросов
• Аналитика платформы (в агрегированном виде)

<b>Что мы НЕ делаем:</b>
• Не продаём данные третьим лицам
• Не используем данные для рекламы без согласия
• Не храним переписку после ответа AI
• Не передаём данные без законного основания

<b>Твои права (GDPR / ФЗ-152):</b>
• Просмотр данных: /mydata
• Исправление: обратись к @support
• Удаление всех данных: /deletedata
• Возражение против обработки: /deletedata

<b>Хранение:</b> данные хранятся на защищённых серверах,
до момента удаления или запроса пользователя.

<i>Используя бота, ты соглашаешься с этой политикой.</i>"""


# ──────────────────────────────────────────────
# Команды
# ──────────────────────────────────────────────

@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    """Показывает политику конфиденциальности."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Мои данные", callback_data="mydata"),
            InlineKeyboardButton(text="🗑 Удалить данные", callback_data="deletedata_confirm"),
        ],
    ])
    await message.answer(PRIVACY_TEXT, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("mydata"))
async def cmd_mydata(message: Message):
    """Показывает все данные, хранящиеся о пользователе."""
    data = await get_full_user_data(message.from_user.id)
    if not data:
        await message.answer("Данные не найдены. Возможно, ты ещё не зарегистрирован.")
        return
    await _send_user_data(message, data)


@router.callback_query(F.data == "mydata")
async def cb_mydata(callback: CallbackQuery):
    data = await get_full_user_data(callback.from_user.id)
    if not data:
        await callback.answer("Данные не найдены", show_alert=True)
        return
    await _send_user_data(callback.message, data)
    await callback.answer()


@router.message(Command("deletedata"))
async def cmd_deletedata(message: Message):
    """Запрос на удаление персональных данных."""
    await _ask_delete_confirm(message)


@router.callback_query(F.data == "deletedata_confirm")
async def cb_deletedata_confirm(callback: CallbackQuery):
    await _ask_delete_confirm(callback.message)
    await callback.answer()


@router.callback_query(F.data == "deletedata_yes")
async def cb_deletedata_yes(callback: CallbackQuery):
    """Подтверждение удаления данных."""
    deleted = await delete_user_data(callback.from_user.id)
    if deleted:
        await callback.message.edit_text(
            "✅ <b>Данные удалены</b>\n\n"
            "Твои персональные данные анонимизированы:\n"
            "• Имя и @username удалены\n"
            "• Демографический профиль удалён\n"
            "• Подписки сброшены\n\n"
            "Агрегированная статистика (без привязки к тебе) "
            "может сохраняться для аналитики платформы.\n\n"
            "<i>Ты можешь продолжить пользоваться ботом — "
            "новые данные не будут связаны со старыми.</i>",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text("❌ Ошибка удаления. Обратись к @support.")
    await callback.answer()


@router.callback_query(F.data == "deletedata_no")
async def cb_deletedata_no(callback: CallbackQuery):
    await callback.message.edit_text(
        "↩️ Удаление отменено. Твои данные сохранены.\n\n"
        "/privacy — вернуться к политике конфиденциальности"
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

async def _send_user_data(message: Message, data: dict) -> None:
    """Форматирует и отправляет данные пользователю."""
    profile = data.get("profile", {})

    tier = "Expert" if data.get("is_expert") else ("Pro" if data.get("is_pro") else "Free")
    pro_until = f" до {data['pro_until']}" if data.get("pro_until") else ""

    lines = [
        "📋 <b>Твои данные на платформе</b>\n",
        f"• <b>Telegram ID:</b> {data['telegram_id']}",
        f"• <b>Имя:</b> {data.get('full_name') or '—'}",
        f"• <b>Username:</b> @{data.get('username') or '—'}",
        f"• <b>Тариф:</b> {tier}{pro_until}",
        f"• <b>Интерес:</b> {data.get('interest') or '—'}",
        f"• <b>Запросов всего:</b> {data.get('total_requests', 0)}",
        f"• <b>Дата регистрации:</b> {data.get('registered_at', '—')[:10]}",
    ]

    if profile:
        lines.append("\n<b>Демографический профиль:</b>")
        if profile.get("age_group"):
            lines.append(f"• Возрастная группа: {profile['age_group']}")
        if profile.get("gender"):
            lines.append(f"• Пол: {profile['gender']}")
        if profile.get("audience_type"):
            lines.append(f"• Тип аудитории: {profile['audience_type']}")
        if profile.get("language"):
            lines.append(f"• Язык: {profile['language']}")
        if profile.get("branches"):
            lines.append(f"• Ветки: {profile['branches']}")

    lines.append("\n<i>Для удаления всех данных используй /deletedata</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _ask_delete_confirm(message: Message) -> None:
    """Запрашивает подтверждение перед удалением данных."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data="deletedata_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="deletedata_no"),
        ],
    ])
    await message.answer(
        "⚠️ <b>Удаление персональных данных</b>\n\n"
        "Будут удалены:\n"
        "• Имя и @username\n"
        "• Демографический профиль\n"
        "• Тариф и история подписок\n"
        "• Выбранный интерес\n\n"
        "Это действие <b>необратимо</b>.\n"
        "Ты уверен?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
