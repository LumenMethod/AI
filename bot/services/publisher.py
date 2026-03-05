"""Мульти-платформенный публикатор: Telegram, Instagram, Facebook."""
import io
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from aiogram import Bot

from bot.services.image_generator import generate_image
from config.settings import settings

logger = logging.getLogger(__name__)

# Meta Graph API
_META_API = "https://graph.facebook.com/v19.0"


class Platform(str, Enum):
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


@dataclass
class PublishResult:
    platform: Platform
    success: bool
    post_id: str = ""
    error: str = ""


# ──────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────

async def _publish_telegram(
    bot: Bot,
    channel: str,
    text: str,
    image_bytes: Optional[bytes],
) -> PublishResult:
    try:
        if image_bytes:
            msg = await bot.send_photo(
                chat_id=channel,
                photo=io.BytesIO(image_bytes),
                caption=text[:1024],  # Telegram caption limit
                parse_mode="HTML",
            )
        else:
            msg = await bot.send_message(channel, text, parse_mode="HTML")
        return PublishResult(Platform.TELEGRAM, True, post_id=str(msg.message_id))
    except Exception as e:
        logger.error(f"Telegram publish error [{channel}]: {e}")
        return PublishResult(Platform.TELEGRAM, False, error=str(e))


# ──────────────────────────────────────────────
# Instagram (Meta Graph API)
# ──────────────────────────────────────────────

async def _upload_instagram_media(
    client: httpx.AsyncClient,
    image_url: str,
    caption: str,
) -> str | None:
    """Шаг 1: создать медиа-контейнер, вернуть creation_id."""
    resp = await client.post(
        f"{_META_API}/{settings.INSTAGRAM_ACCOUNT_ID}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": settings.META_ACCESS_TOKEN,
        },
        timeout=30,
    )
    data = resp.json()
    if "id" not in data:
        logger.error(f"Instagram media create error: {data}")
        return None
    return data["id"]


async def _publish_instagram(
    text: str,
    image_url: Optional[str],
) -> PublishResult:
    if not (settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID):
        return PublishResult(Platform.INSTAGRAM, False, error="Meta credentials not configured")
    if not image_url:
        return PublishResult(Platform.INSTAGRAM, False, error="Instagram requires an image")

    # Instagram caption limit — 2200 символов
    caption = text[:2200]

    try:
        async with httpx.AsyncClient() as client:
            creation_id = await _upload_instagram_media(client, image_url, caption)
            if not creation_id:
                return PublishResult(Platform.INSTAGRAM, False, error="Media upload failed")

            # Шаг 2: опубликовать контейнер
            resp = await client.post(
                f"{_META_API}/{settings.INSTAGRAM_ACCOUNT_ID}/media_publish",
                params={
                    "creation_id": creation_id,
                    "access_token": settings.META_ACCESS_TOKEN,
                },
                timeout=30,
            )
            data = resp.json()
            if "id" not in data:
                logger.error(f"Instagram publish error: {data}")
                return PublishResult(Platform.INSTAGRAM, False, error=str(data))

            return PublishResult(Platform.INSTAGRAM, True, post_id=data["id"])

    except Exception as e:
        logger.error(f"Instagram publish exception: {e}")
        return PublishResult(Platform.INSTAGRAM, False, error=str(e))


# ──────────────────────────────────────────────
# Facebook (Pages API)
# ──────────────────────────────────────────────

async def _publish_facebook(
    text: str,
    image_url: Optional[str],
) -> PublishResult:
    if not (settings.META_ACCESS_TOKEN and settings.FACEBOOK_PAGE_ID):
        return PublishResult(Platform.FACEBOOK, False, error="Meta credentials not configured")

    params: dict = {
        "message": text[:63206],  # Facebook post limit
        "access_token": settings.META_ACCESS_TOKEN,
    }
    endpoint = f"{_META_API}/{settings.FACEBOOK_PAGE_ID}/feed"

    if image_url:
        # Публикуем с фото через /photos endpoint
        endpoint = f"{_META_API}/{settings.FACEBOOK_PAGE_ID}/photos"
        params["url"] = image_url

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, params=params)
            data = resp.json()
            post_id = data.get("id") or data.get("post_id")
            if not post_id:
                logger.error(f"Facebook publish error: {data}")
                return PublishResult(Platform.FACEBOOK, False, error=str(data))
            return PublishResult(Platform.FACEBOOK, True, post_id=post_id)

    except Exception as e:
        logger.error(f"Facebook publish exception: {e}")
        return PublishResult(Platform.FACEBOOK, False, error=str(e))


# ──────────────────────────────────────────────
# Единый интерфейс
# ──────────────────────────────────────────────

async def publish(
    bot: Bot,
    branch: str,
    text: str,
    channel: Optional[str] = None,
    platforms: list[Platform] | None = None,
    image_url: Optional[str] = None,
) -> list[PublishResult]:
    """
    Публикует `text` на указанных платформах.

    Args:
        bot: экземпляр aiogram Bot
        branch: ветка контента (health/finance/tech/news/edu/main)
        text: текст поста
        channel: Telegram channel ID/username (если None — используется CHANNEL_ID)
        platforms: список платформ; если None — только Telegram
        image_url: публичный URL картинки для Instagram/Facebook
    """
    if platforms is None:
        platforms = [Platform.TELEGRAM]

    # Генерируем картинку через DALL-E если нужна и URL не передан
    image_bytes: Optional[bytes] = None
    if Platform.TELEGRAM in platforms or (not image_url and len(platforms) > 0):
        if settings.OPENAI_API_KEY:
            image_bytes = await generate_image(branch, text)

    results: list[PublishResult] = []

    for platform in platforms:
        if platform == Platform.TELEGRAM:
            tg_channel = channel or settings.CHANNEL_ID
            if tg_channel:
                result = await _publish_telegram(bot, tg_channel, text, image_bytes)
                results.append(result)
                if result.success:
                    logger.info(f"Published to Telegram [{tg_channel}]")

        elif platform == Platform.INSTAGRAM:
            result = await _publish_instagram(text, image_url)
            results.append(result)
            if result.success:
                logger.info(f"Published to Instagram: post_id={result.post_id}")

        elif platform == Platform.FACEBOOK:
            result = await _publish_facebook(text, image_url)
            results.append(result)
            if result.success:
                logger.info(f"Published to Facebook: post_id={result.post_id}")

    return results
