"""Мульти-платформенный публикатор: Telegram, Instagram, Facebook, X, TikTok."""
import io
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
import tweepy
from aiogram import Bot

from bot.services.image_generator import generate_image
from config.settings import settings

logger = logging.getLogger(__name__)

# Meta Graph API
_META_API = "https://graph.facebook.com/v19.0"
# TikTok Content Posting API
_TIKTOK_API = "https://open.tiktokapis.com/v2"


class Platform(str, Enum):
    TELEGRAM  = "telegram"
    INSTAGRAM = "instagram"
    FACEBOOK  = "facebook"
    TWITTER   = "twitter"   # X
    TIKTOK    = "tiktok"


@dataclass
class PublishResult:
    platform: Platform
    success: bool
    post_id: str = ""
    error: str = ""


def _strip_html(text: str) -> str:
    """Убирает HTML-теги для платформ, не поддерживающих разметку."""
    return re.sub(r"<[^>]+>", "", text).strip()


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
                caption=text[:1024],
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


async def _publish_instagram(text: str, image_url: Optional[str]) -> PublishResult:
    if not (settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID):
        return PublishResult(Platform.INSTAGRAM, False, error="Meta credentials not configured")
    if not image_url:
        return PublishResult(Platform.INSTAGRAM, False, error="Instagram requires an image")

    caption = _strip_html(text)[:2200]
    try:
        async with httpx.AsyncClient() as client:
            creation_id = await _upload_instagram_media(client, image_url, caption)
            if not creation_id:
                return PublishResult(Platform.INSTAGRAM, False, error="Media upload failed")
            resp = await client.post(
                f"{_META_API}/{settings.INSTAGRAM_ACCOUNT_ID}/media_publish",
                params={"creation_id": creation_id, "access_token": settings.META_ACCESS_TOKEN},
                timeout=30,
            )
            data = resp.json()
            if "id" not in data:
                return PublishResult(Platform.INSTAGRAM, False, error=str(data))
            return PublishResult(Platform.INSTAGRAM, True, post_id=data["id"])
    except Exception as e:
        logger.error(f"Instagram publish exception: {e}")
        return PublishResult(Platform.INSTAGRAM, False, error=str(e))


# ──────────────────────────────────────────────
# Facebook (Pages API)
# ──────────────────────────────────────────────

async def _publish_facebook(text: str, image_url: Optional[str]) -> PublishResult:
    if not (settings.META_ACCESS_TOKEN and settings.FACEBOOK_PAGE_ID):
        return PublishResult(Platform.FACEBOOK, False, error="Meta credentials not configured")

    clean = _strip_html(text)
    params: dict = {"message": clean[:63206], "access_token": settings.META_ACCESS_TOKEN}
    endpoint = f"{_META_API}/{settings.FACEBOOK_PAGE_ID}/feed"
    if image_url:
        endpoint = f"{_META_API}/{settings.FACEBOOK_PAGE_ID}/photos"
        params["url"] = image_url

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, params=params)
            data = resp.json()
            post_id = data.get("id") or data.get("post_id")
            if not post_id:
                return PublishResult(Platform.FACEBOOK, False, error=str(data))
            return PublishResult(Platform.FACEBOOK, True, post_id=post_id)
    except Exception as e:
        logger.error(f"Facebook publish exception: {e}")
        return PublishResult(Platform.FACEBOOK, False, error=str(e))


# ──────────────────────────────────────────────
# X (Twitter) — API v2 через tweepy
# ──────────────────────────────────────────────

def _get_twitter_client() -> tweepy.AsyncClient | None:
    if not all([
        settings.TWITTER_API_KEY,
        settings.TWITTER_API_SECRET,
        settings.TWITTER_ACCESS_TOKEN,
        settings.TWITTER_ACCESS_TOKEN_SECRET,
    ]):
        return None
    return tweepy.AsyncClient(
        consumer_key=settings.TWITTER_API_KEY,
        consumer_secret=settings.TWITTER_API_SECRET,
        access_token=settings.TWITTER_ACCESS_TOKEN,
        access_token_secret=settings.TWITTER_ACCESS_TOKEN_SECRET,
    )


async def _publish_twitter(text: str, image_bytes: Optional[bytes]) -> PublishResult:
    client = _get_twitter_client()
    if not client:
        return PublishResult(Platform.TWITTER, False, error="X credentials not configured")

    # X: лимит 280 символов, без HTML
    tweet_text = _strip_html(text)[:280]

    media_id: str | None = None
    if image_bytes:
        # Загрузка медиа через v1.1 API (tweepy Auth v1)
        try:
            auth = tweepy.OAuth1UserHandler(
                settings.TWITTER_API_KEY,
                settings.TWITTER_API_SECRET,
                settings.TWITTER_ACCESS_TOKEN,
                settings.TWITTER_ACCESS_TOKEN_SECRET,
            )
            api_v1 = tweepy.API(auth)
            media = api_v1.media_upload(
                filename="post.png",
                file=io.BytesIO(image_bytes),
            )
            media_id = str(media.media_id)
        except Exception as e:
            logger.warning(f"X media upload failed (posting without image): {e}")

    try:
        kwargs: dict = {"text": tweet_text}
        if media_id:
            kwargs["media_ids"] = [media_id]
        response = await client.create_tweet(**kwargs)
        tweet_id = str(response.data["id"])
        return PublishResult(Platform.TWITTER, True, post_id=tweet_id)
    except Exception as e:
        logger.error(f"X publish exception: {e}")
        return PublishResult(Platform.TWITTER, False, error=str(e))


# ──────────────────────────────────────────────
# TikTok — Content Posting API v2
# ──────────────────────────────────────────────

async def _publish_tiktok(text: str, image_bytes: Optional[bytes]) -> PublishResult:
    """
    Публикует фото-пост в TikTok (Photo Mode).
    TikTok требует изображение для фото-поста.
    Если image_bytes не передан — публикация невозможна.
    """
    if not settings.TIKTOK_ACCESS_TOKEN:
        return PublishResult(Platform.TIKTOK, False, error="TikTok credentials not configured")
    if not image_bytes:
        return PublishResult(Platform.TIKTOK, False, error="TikTok requires an image")

    headers = {
        "Authorization": f"Bearer {settings.TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    caption = _strip_html(text)[:2200]

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Шаг 1: инициализировать загрузку (PHOTO_POST)
            init_resp = await client.post(
                f"{_TIKTOK_API}/post/publish/content/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title": caption[:150],
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "photo_cover_index": 0,
                        "photo_images": [],  # URL будет передан после загрузки
                    },
                    "post_mode": "DIRECT_POST",
                    "media_type": "PHOTO",
                },
            )
            init_data = init_resp.json()
            if init_data.get("error", {}).get("code") != "ok":
                logger.error(f"TikTok init error: {init_data}")
                return PublishResult(Platform.TIKTOK, False, error=str(init_data))

            publish_id = init_data["data"]["publish_id"]
            upload_url = init_data["data"].get("upload_url")

            # Шаг 2: загрузить изображение
            if upload_url:
                await client.put(
                    upload_url,
                    content=image_bytes,
                    headers={"Content-Type": "image/png"},
                    timeout=60,
                )

            return PublishResult(Platform.TIKTOK, True, post_id=publish_id)

    except Exception as e:
        logger.error(f"TikTok publish exception: {e}")
        return PublishResult(Platform.TIKTOK, False, error=str(e))


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
        bot:       экземпляр aiogram Bot
        branch:    ветка контента (health/finance/tech/news/edu/main)
        text:      текст поста (HTML-разметка Telegram)
        channel:   Telegram channel ID/username (если None — CHANNEL_ID из настроек)
        platforms: список платформ; если None — только Telegram
        image_url: публичный URL картинки для Instagram/Facebook
    """
    if platforms is None:
        platforms = [Platform.TELEGRAM]

    # Генерируем картинку через DALL-E если ключ задан
    image_bytes: Optional[bytes] = None
    needs_image = any(p in platforms for p in (
        Platform.TELEGRAM, Platform.TWITTER, Platform.TIKTOK
    ))
    if needs_image and settings.OPENAI_API_KEY:
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
                logger.info(f"Published to Instagram: {result.post_id}")

        elif platform == Platform.FACEBOOK:
            result = await _publish_facebook(text, image_url)
            results.append(result)
            if result.success:
                logger.info(f"Published to Facebook: {result.post_id}")

        elif platform == Platform.TWITTER:
            result = await _publish_twitter(text, image_bytes)
            results.append(result)
            if result.success:
                logger.info(f"Published to X: {result.post_id}")

        elif platform == Platform.TIKTOK:
            result = await _publish_tiktok(text, image_bytes)
            results.append(result)
            if result.success:
                logger.info(f"Published to TikTok: {result.post_id}")

    return results
