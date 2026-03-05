"""Генерация изображений через DALL-E 3 для постов экосистемы "Человек 2035"."""
import hashlib
import logging
import os
from pathlib import Path

import httpx
import openai

from config.settings import settings

logger = logging.getLogger(__name__)

# Папка для кеша изображений
_CACHE_DIR = Path(os.getenv("IMAGE_CACHE_DIR", "./image_cache"))

# Стилистическая база для всех промптов
_STYLE_BASE = (
    "Minimalist futuristic illustration, clean design, "
    "deep blue and cyan gradient background, subtle geometric patterns, "
    "no text, no people faces, ultra HD, professional digital art"
)

# Стилевые акценты по веткам
_BRANCH_STYLE = {
    "health":  "glowing DNA helix, human silhouette with biopulse lines, green bio-energy",
    "finance": "golden coins floating, blockchain nodes, upward graphs, wealth visualization",
    "tech":    "neural network circuits, robotic hand, holographic UI, electric blue sparks",
    "news":    "globe with light streams, satellite orbits, information flow, silver tones",
    "edu":     "open book with light beam, graduation cap, glowing knowledge symbols, warm amber",
    "main":    "Earth from space with digital overlay, humanity silhouettes, cosmic horizon",
}


def _cache_path(prompt_hash: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{prompt_hash}.png"


def _prompt_hash(prompt: str) -> str:
    return hashlib.md5(prompt.encode()).hexdigest()


async def generate_image(branch: str, post_text: str) -> bytes | None:
    """
    Генерирует изображение для поста.
    Возвращает PNG-байты или None при ошибке / отсутствии API-ключа.
    Кеширует результат локально.
    """
    if not settings.OPENAI_API_KEY:
        logger.debug("OPENAI_API_KEY not set — image generation skipped")
        return None

    branch_accent = _BRANCH_STYLE.get(branch, _BRANCH_STYLE["main"])
    # Берём первые 120 символов поста как тематический контекст
    context = post_text[:120].strip().replace("\n", " ")
    full_prompt = f"{_STYLE_BASE}, {branch_accent}. Theme context: {context}"

    cache_file = _cache_path(_prompt_hash(full_prompt))
    if cache_file.exists():
        logger.debug(f"Image cache hit: {cache_file.name}")
        return cache_file.read_bytes()

    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url

        async with httpx.AsyncClient(timeout=30) as http:
            img_response = await http.get(image_url)
            img_response.raise_for_status()
            image_bytes = img_response.content

        cache_file.write_bytes(image_bytes)
        logger.info(f"Image generated and cached: {cache_file.name}")
        return image_bytes

    except openai.OpenAIError as e:
        logger.error(f"DALL-E 3 error [{branch}]: {e}")
        return None
    except Exception as e:
        logger.error(f"Image generation unexpected error: {e}")
        return None
