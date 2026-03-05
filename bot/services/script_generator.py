"""Генератор сценариев для YouTube — Shorts и длинных видео.

Каждый сценарий привязан к персоне ветки (BRANCH_PERSONAS)
и строится под конкретный формат:

  • Shorts (~60 сек, ~140 слов) — вертикальное видео
  • Long (~10-15 мин) — полноценный разбор темы
"""
import logging
from dataclasses import dataclass, field

import anthropic

from bot.services.content_generator import BRANCH_PERSONAS, BRANCH_META, SUPPORTED_LANGUAGES
from config.settings import settings

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


# ──────────────────────────────────────────────
# Типы данных
# ──────────────────────────────────────────────

@dataclass
class ShortsScript:
    """Сценарий для YouTube Shorts (~60 сек)."""
    branch: str
    language: str
    hook: str          # 0-3 сек — захват внимания (1 предложение)
    points: list[str]  # 3-50 сек — 3 ключевых тезиса
    cta: str           # 50-60 сек — призыв к действию
    title: str         # Заголовок видео (до 100 символов)
    description: str   # Описание (до 500 символов)
    tags: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        """Полный сценарий как читаемый текст."""
        points_block = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(self.points))
        return (
            f"🎬 SHORTS: {self.title}\n"
            f"{'─' * 50}\n\n"
            f"[ХУК — 0-3 сек]\n{self.hook}\n\n"
            f"[ОСНОВНОЙ БЛОК — 3-50 сек]\n{points_block}\n\n"
            f"[ПРИЗЫВ — 50-60 сек]\n{self.cta}\n\n"
            f"{'─' * 50}\n"
            f"📋 Описание:\n{self.description}\n\n"
            f"🏷 Теги: {', '.join(self.tags)}"
        )


@dataclass
class VideoBlock:
    """Блок длинного видео."""
    title: str     # Название блока / таймкод
    content: str   # Что говорит ведущий


@dataclass
class VideoScript:
    """Сценарий длинного YouTube-видео (10-15 мин)."""
    branch: str
    language: str
    duration_minutes: int
    title: str
    description: str
    intro: str           # ~1 мин — приветствие и тезис видео
    blocks: list[VideoBlock]  # 5-7 блоков основной части
    outro: str           # ~1 мин — итоги + призыв подписаться
    tags: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        """Полный сценарий как читаемый текст."""
        lines = [
            f"🎬 ВИДЕО ({self.duration_minutes} мин): {self.title}",
            "─" * 60,
            "",
            f"[ИНТРО — ~1 мин]",
            self.intro,
            "",
        ]
        for i, block in enumerate(self.blocks):
            lines += [f"[БЛОК {i+1}: {block.title}]", block.content, ""]
        lines += [
            f"[АУТРО — ~1 мин]",
            self.outro,
            "",
            "─" * 60,
            f"📋 Описание:\n{self.description}",
            "",
            f"🏷 Теги: {', '.join(self.tags)}",
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────
# Генератор Shorts
# ──────────────────────────────────────────────

async def generate_shorts_script(
    branch: str,
    topic: str | None = None,
    language: str = "ru",
) -> ShortsScript:
    """
    Генерирует сценарий YouTube Shorts (~60 сек).

    Args:
        branch:   ветка (health/finance/tech/news/edu)
        topic:    тема видео (если None — Claude выбирает сам)
        language: код языка из SUPPORTED_LANGUAGES
    """
    persona = BRANCH_PERSONAS.get(branch, BRANCH_PERSONAS["tech"])
    meta = BRANCH_META.get(branch, BRANCH_META["tech"])
    lang_name = SUPPORTED_LANGUAGES.get(language, language)
    topic_line = f"Тема видео: {topic}" if topic else f"Выбери актуальную тему из области: {meta['focus']}"

    system = (
        f"Ты — {persona['name']}, {persona['role']}.\n"
        f"Стиль: {persona['style']}\n"
        f"Ты создаёшь сценарии для YouTube Shorts. Говоришь только на {lang_name}."
    )

    prompt = (
        f"{topic_line}\n\n"
        f"Создай сценарий YouTube Shorts (60 секунд) для канала «{meta['name']}».\n\n"
        f"Ответь строго в формате:\n"
        f"TITLE: <заголовок до 100 символов>\n"
        f"HOOK: <фраза-хук 0-3 сек — одно предложение, провокационное или неожиданное>\n"
        f"POINT1: <тезис 1 — конкретный факт или совет>\n"
        f"POINT2: <тезис 2>\n"
        f"POINT3: <тезис 3>\n"
        f"CTA: <призыв к действию 50-60 сек — подписаться / сохранить / применить>\n"
        f"DESC: <описание видео до 500 символов с хэштегами {meta['hashtags']}>\n"
        f"TAGS: <теги через запятую, 10-15 штук>\n\n"
        f"Язык: {lang_name}. Без лишних пояснений — только формат выше."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=700,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_shorts(message.content[0].text, branch, language)


def _parse_shorts(raw: str, branch: str, language: str) -> ShortsScript:
    """Парсит ответ Claude в ShortsScript."""
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip().upper()] = val.strip()

    points = [
        data.get("POINT1", ""),
        data.get("POINT2", ""),
        data.get("POINT3", ""),
    ]
    tags_raw = data.get("TAGS", "")
    tags = [t.strip().lstrip("#") for t in tags_raw.split(",") if t.strip()]

    return ShortsScript(
        branch=branch,
        language=language,
        title=data.get("TITLE", "Shorts"),
        hook=data.get("HOOK", ""),
        points=[p for p in points if p],
        cta=data.get("CTA", ""),
        description=data.get("DESC", ""),
        tags=tags,
    )


# ──────────────────────────────────────────────
# Генератор длинного видео
# ──────────────────────────────────────────────

async def generate_video_script(
    branch: str,
    topic: str | None = None,
    duration_minutes: int = 12,
    language: str = "ru",
) -> VideoScript:
    """
    Генерирует сценарий длинного YouTube-видео.

    Args:
        branch:           ветка (health/finance/tech/news/edu)
        topic:            тема видео (если None — Claude выбирает)
        duration_minutes: желаемая длительность в минутах (10-20)
        language:         код языка
    """
    persona = BRANCH_PERSONAS.get(branch, BRANCH_PERSONAS["tech"])
    meta = BRANCH_META.get(branch, BRANCH_META["tech"])
    lang_name = SUPPORTED_LANGUAGES.get(language, language)
    topic_line = f"Тема видео: {topic}" if topic else f"Выбери актуальную тему из области: {meta['focus']}"

    # Количество блоков зависит от длины
    num_blocks = max(5, min(8, duration_minutes // 2))

    system = (
        f"Ты — {persona['name']}, {persona['role']}.\n"
        f"Стиль: {persona['style']}\n"
        f"Ты создаёшь подробные сценарии для YouTube. Язык: {lang_name}."
    )

    prompt = (
        f"{topic_line}\n\n"
        f"Создай сценарий YouTube-видео на {duration_minutes} минут для канала «{meta['name']}».\n"
        f"Блоков основной части: {num_blocks}.\n\n"
        f"Ответь строго в формате:\n"
        f"TITLE: <заголовок до 100 символов>\n"
        f"INTRO: <вступление ~1 мин — приветствие, проблема, что узнает зритель>\n"
        f"BLOCK1_TITLE: <название блока 1>\n"
        f"BLOCK1: <содержание блока 1, 100-150 слов>\n"
        f"...\n"
        f"BLOCK{num_blocks}_TITLE: <название>\n"
        f"BLOCK{num_blocks}: <содержание>\n"
        f"OUTRO: <заключение ~1 мин — итог + призыв подписаться>\n"
        f"DESC: <описание видео до 800 символов с хэштегами {meta['hashtags']}>\n"
        f"TAGS: <теги через запятую, 15-20 штук>\n\n"
        f"Язык: {lang_name}. Конкретика, примеры, факты. Без воды."
    )

    message = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_video(message.content[0].text, branch, language, duration_minutes, num_blocks)


def _parse_video(
    raw: str,
    branch: str,
    language: str,
    duration_minutes: int,
    num_blocks: int,
) -> VideoScript:
    """Парсит ответ Claude в VideoScript."""
    data: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        if ":" in line:
            first, _, rest = line.partition(":")
            key = first.strip().upper()
            if key and (key.startswith("BLOCK") or key in (
                "TITLE", "INTRO", "OUTRO", "DESC", "TAGS"
            )):
                if current_key:
                    data[current_key] = " ".join(current_lines).strip()
                current_key = key
                current_lines = [rest.strip()] if rest.strip() else []
                continue
        if current_key:
            current_lines.append(line)

    if current_key:
        data[current_key] = " ".join(current_lines).strip()

    blocks: list[VideoBlock] = []
    for i in range(1, num_blocks + 1):
        title = data.get(f"BLOCK{i}_TITLE", f"Блок {i}")
        content = data.get(f"BLOCK{i}", "")
        if content:
            blocks.append(VideoBlock(title=title, content=content))

    tags_raw = data.get("TAGS", "")
    tags = [t.strip().lstrip("#") for t in tags_raw.split(",") if t.strip()]

    return VideoScript(
        branch=branch,
        language=language,
        duration_minutes=duration_minutes,
        title=data.get("TITLE", "Видео"),
        intro=data.get("INTRO", ""),
        blocks=blocks,
        outro=data.get("OUTRO", ""),
        description=data.get("DESC", ""),
        tags=tags,
    )
