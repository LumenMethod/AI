"""YouTube Data API v3 — загрузка видео и статистика канала.

Аутентификация: OAuth 2.0 (Desktop App flow).

Как получить credentials:
  1. console.cloud.google.com → New Project
  2. APIs & Services → Enable → YouTube Data API v3
  3. Credentials → Create → OAuth 2.0 Client ID → Desktop App → Download JSON
  4. Содержимое client_secret_*.json → переменная YOUTUBE_CREDENTIALS_JSON
  5. При первом запуске generate_token() откроет браузер для авторизации
  6. Полученный token.json → переменная YOUTUBE_TOKEN_JSON (обновляется автоматически)

Требуемые scopes:
  - https://www.googleapis.com/auth/youtube.upload
  - https://www.googleapis.com/auth/youtube.readonly
"""
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass
class YouTubeUploadResult:
    success: bool
    video_id: str = ""
    video_url: str = ""
    error: str = ""


# ──────────────────────────────────────────────
# OAuth2 — получение и обновление токена
# ──────────────────────────────────────────────

class YouTubeAuth:
    """Управляет OAuth2-токеном для YouTube."""

    def __init__(self):
        self._token: dict = {}
        self._credentials: dict = {}
        self._loaded = False

    def _load(self) -> bool:
        if self._loaded:
            return bool(self._token)

        creds_raw = settings.YOUTUBE_CREDENTIALS_JSON
        token_raw = settings.YOUTUBE_TOKEN_JSON

        if not creds_raw or not token_raw:
            logger.warning("YouTube credentials not configured (YOUTUBE_CREDENTIALS_JSON / YOUTUBE_TOKEN_JSON)")
            return False

        try:
            self._credentials = json.loads(creds_raw).get("installed") or json.loads(creds_raw).get("web") or {}
            self._token = json.loads(token_raw)
            self._loaded = True
            return True
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"YouTube credentials parse error: {e}")
            return False

    async def get_access_token(self) -> str | None:
        """Возвращает валидный access token, обновляет если истёк."""
        if not self._load():
            return None

        # Проверяем истечение через refresh
        if not self._token.get("access_token"):
            return None

        if self._token.get("refresh_token"):
            refreshed = await self._refresh()
            if refreshed:
                return self._token["access_token"]

        return self._token.get("access_token")

    async def _refresh(self) -> bool:
        """Обновляет access token через refresh token."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": self._credentials.get("client_id", ""),
                        "client_secret": self._credentials.get("client_secret", ""),
                        "refresh_token": self._token["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                data = resp.json()
                if "access_token" in data:
                    self._token["access_token"] = data["access_token"]
                    logger.debug("YouTube access token refreshed")
                    return True
                logger.error(f"YouTube token refresh failed: {data}")
                return False
        except Exception as e:
            logger.error(f"YouTube token refresh exception: {e}")
            return False


_auth = YouTubeAuth()


# ──────────────────────────────────────────────
# Загрузка видео
# ──────────────────────────────────────────────

async def upload_video(
    file_path: str | Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "22",       # 22 = People & Blogs, 28 = Science & Technology
    privacy: str | None = None,
    is_shorts: bool = False,
) -> YouTubeUploadResult:
    """
    Загружает MP4-видео на YouTube.

    Args:
        file_path:    путь к видеофайлу
        title:        заголовок (до 100 символов)
        description:  описание
        tags:         список тегов
        category_id:  ID категории YouTube (22 = People & Blogs)
        privacy:      public | unlisted | private (None → из настроек)
        is_shorts:    если True — добавляет #Shorts в title и description

    Returns:
        YouTubeUploadResult
    """
    access_token = await _auth.get_access_token()
    if not access_token:
        return YouTubeUploadResult(False, error="YouTube not authenticated. Configure YOUTUBE_CREDENTIALS_JSON and YOUTUBE_TOKEN_JSON.")

    file_path = Path(file_path)
    if not file_path.exists():
        return YouTubeUploadResult(False, error=f"File not found: {file_path}")

    privacy_status = privacy or settings.YOUTUBE_DEFAULT_PRIVACY

    # Shorts: #Shorts в заголовке обязателен для попадания в ленту
    if is_shorts:
        if "#Shorts" not in title:
            title = f"{title} #Shorts"
        if "#Shorts" not in description:
            description = f"{description}\n\n#Shorts"

    video_metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    file_size = file_path.stat().st_size
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(file_size),
        "Content-Type": "application/json; charset=UTF-8",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Шаг 1: инициализируем resumable upload
            init_resp = await client.post(
                _UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers=headers,
                content=json.dumps(video_metadata).encode(),
            )

            if init_resp.status_code != 200:
                return YouTubeUploadResult(
                    False, error=f"Init upload failed: {init_resp.status_code} {init_resp.text}"
                )

            upload_uri = init_resp.headers.get("Location")
            if not upload_uri:
                return YouTubeUploadResult(False, error="No upload URI in response")

            # Шаг 2: загружаем файл
            with open(file_path, "rb") as f:
                upload_resp = await client.put(
                    upload_uri,
                    content=f.read(),
                    headers={"Content-Type": "video/mp4"},
                    timeout=600,  # большие файлы
                )

            if upload_resp.status_code not in (200, 201):
                return YouTubeUploadResult(
                    False, error=f"Upload failed: {upload_resp.status_code} {upload_resp.text[:300]}"
                )

            data = upload_resp.json()
            video_id = data.get("id", "")
            video_url = f"https://youtu.be/{video_id}" if video_id else ""

            logger.info(f"YouTube upload success: {video_url}")
            return YouTubeUploadResult(True, video_id=video_id, video_url=video_url)

    except Exception as e:
        logger.error(f"YouTube upload exception: {e}")
        return YouTubeUploadResult(False, error=str(e))


# ──────────────────────────────────────────────
# Статистика канала
# ──────────────────────────────────────────────

async def get_channel_stats() -> dict:
    """
    Возвращает статистику YouTube-канала.

    Returns:
        dict: subscribers, views, videos, title
    """
    access_token = await _auth.get_access_token()
    if not access_token:
        return {"error": "not_authenticated"}

    params: dict = {
        "part": "snippet,statistics",
        "mine": "true",
    }
    if settings.YOUTUBE_CHANNEL_ID:
        params = {
            "part": "snippet,statistics",
            "id": settings.YOUTUBE_CHANNEL_ID,
        }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                _CHANNEL_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return {"error": "channel_not_found"}

            item = items[0]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            return {
                "title": snippet.get("title", ""),
                "subscribers": int(stats.get("subscriberCount", 0)),
                "views": int(stats.get("viewCount", 0)),
                "videos": int(stats.get("videoCount", 0)),
            }
    except Exception as e:
        logger.error(f"YouTube stats exception: {e}")
        return {"error": str(e)}
