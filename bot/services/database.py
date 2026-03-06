"""База данных — модели и операции для платформы "Человек 2035"."""
import hashlib
from datetime import date, datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date, Text,
    select, update, func,
)
from config.settings import settings


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# Существующие таблицы
# ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=True)
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    is_expert: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    daily_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_request_date: Mapped[date] = mapped_column(Date, nullable=True)
    interest: Mapped[str] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)


# ──────────────────────────────────────────────
# Новые таблицы (Этап 3)
# ──────────────────────────────────────────────

class UserProfile(Base):
    """Демографический профиль пользователя для персонализации контента."""
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    # Демография
    age_group: Mapped[str] = mapped_column(String(16), nullable=True)
    # gen_z (18-25) | millennial (26-40) | gen_x (41-55) | boomer (55+)

    gender: Mapped[str] = mapped_column(String(16), nullable=True)
    # male | female | other | not_specified

    audience_type: Mapped[str] = mapped_column(String(32), nullable=True)
    # general | lgbtq | professional | student

    # Контент-предпочтения
    language: Mapped[str] = mapped_column(String(8), default="ru")
    branches: Mapped[str] = mapped_column(String(128), nullable=True)
    # Разделённый запятой список: "health,finance,tech"

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PublishedPost(Base):
    """Лог опубликованных постов для аналитики и дедупликации."""
    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch: Mapped[str] = mapped_column(String(32), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    # telegram | instagram | facebook | twitter | tiktok
    language: Mapped[str] = mapped_column(String(8), default="ru")
    content_hash: Mapped[str] = mapped_column(String(32), index=True)
    post_id: Mapped[str] = mapped_column(String(64), nullable=True)
    title_preview: Mapped[str] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class NewsSource(Base):
    """Управляемые RSS-источники новостей."""
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    # health | finance | tech | news | edu
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ──────────────────────────────────────────────
# User — существующие функции
# ──────────────────────────────────────────────

async def get_or_create_user(telegram_id: int, username: str = None, full_name: str = None) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def check_and_increment_requests(telegram_id: int) -> bool:
    """Returns True if request is allowed, False if limit exceeded."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return False

        today = date.today()

        if user.is_pro or user.is_expert:
            await session.execute(
                update(User).where(User.telegram_id == telegram_id)
                .values(total_requests=User.total_requests + 1)
            )
            await session.commit()
            return True

        if user.last_request_date != today:
            await session.execute(
                update(User).where(User.telegram_id == telegram_id)
                .values(daily_requests=1, last_request_date=today, total_requests=User.total_requests + 1)
            )
            await session.commit()
            return True

        if user.daily_requests >= settings.FREE_DAILY_LIMIT:
            return False

        await session.execute(
            update(User).where(User.telegram_id == telegram_id)
            .values(daily_requests=User.daily_requests + 1, total_requests=User.total_requests + 1)
        )
        await session.commit()
        return True


async def set_user_interest(telegram_id: int, interest: str):
    async with async_session() as session:
        await session.execute(
            update(User).where(User.telegram_id == telegram_id).values(interest=interest)
        )
        await session.commit()


async def get_user_stats(telegram_id: int) -> dict:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return {}
        today = date.today()
        daily = user.daily_requests if user.last_request_date == today else 0
        return {
            "is_pro": user.is_pro,
            "is_expert": user.is_expert,
            "daily_requests": daily,
            "total_requests": user.total_requests,
            "interest": user.interest,
        }


# ──────────────────────────────────────────────
# UserProfile — новые функции
# ──────────────────────────────────────────────

async def get_or_create_profile(telegram_id: int) -> UserProfile:
    async with async_session() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.telegram_id == telegram_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            profile = UserProfile(telegram_id=telegram_id)
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
        return profile


async def update_user_profile(telegram_id: int, **fields) -> None:
    """Обновляет поля профиля. fields: age_group, gender, audience_type, language, branches."""
    fields["updated_at"] = datetime.utcnow()
    async with async_session() as session:
        await session.execute(
            update(UserProfile).where(UserProfile.telegram_id == telegram_id).values(**fields)
        )
        await session.commit()


# ──────────────────────────────────────────────
# PublishedPost — новые функции
# ──────────────────────────────────────────────

def _content_hash(text: str) -> str:
    return hashlib.md5(text[:300].encode()).hexdigest()


async def log_published_post(
    branch: str,
    platform: str,
    text: str,
    language: str = "ru",
    post_id: str = "",
    title_preview: str = "",
) -> PublishedPost:
    async with async_session() as session:
        post = PublishedPost(
            branch=branch,
            platform=platform,
            language=language,
            content_hash=_content_hash(text),
            post_id=post_id,
            title_preview=title_preview[:200],
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post


async def get_branch_last_post(branch: str) -> datetime | None:
    """Возвращает время последнего поста для ветки."""
    async with async_session() as session:
        result = await session.execute(
            select(PublishedPost.published_at)
            .where(PublishedPost.branch == branch)
            .order_by(PublishedPost.published_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def get_analytics(days: int = 7) -> dict:
    """Статистика публикаций за последние N дней."""
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        total = await session.scalar(
            select(func.count(PublishedPost.id)).where(PublishedPost.published_at >= since)
        )
        rows = await session.execute(
            select(PublishedPost.platform, func.count(PublishedPost.id))
            .where(PublishedPost.published_at >= since)
            .group_by(PublishedPost.platform)
        )
        by_platform = {row[0]: row[1] for row in rows}

        rows = await session.execute(
            select(PublishedPost.branch, func.count(PublishedPost.id))
            .where(PublishedPost.published_at >= since)
            .group_by(PublishedPost.branch)
        )
        by_branch = {row[0]: row[1] for row in rows}

    return {"total": total, "by_platform": by_platform, "by_branch": by_branch, "days": days}


# ──────────────────────────────────────────────
# NewsSource — новые функции
# ──────────────────────────────────────────────

async def get_active_sources(category: str | None = None) -> list[NewsSource]:
    async with async_session() as session:
        q = select(NewsSource).where(NewsSource.is_active == True)
        if category:
            q = q.where(NewsSource.category == category)
        result = await session.execute(q)
        return list(result.scalars().all())


async def add_news_source(url: str, category: str) -> NewsSource:
    async with async_session() as session:
        source = NewsSource(url=url, category=category)
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source


async def toggle_news_source(source_id: int, is_active: bool) -> None:
    async with async_session() as session:
        await session.execute(
            update(NewsSource).where(NewsSource.id == source_id).values(is_active=is_active)
        )
        await session.commit()


async def mark_source_fetched(url: str, failed: bool = False) -> None:
    async with async_session() as session:
        values: dict = {"last_fetched": datetime.utcnow()}
        if failed:
            values["fail_count"] = NewsSource.fail_count + 1
        await session.execute(
            update(NewsSource).where(NewsSource.url == url).values(**values)
        )
        await session.commit()


# ──────────────────────────────────────────────
# Права пользователя — просмотр и удаление данных
# ──────────────────────────────────────────────

async def get_full_user_data(telegram_id: int) -> dict:
    """
    Возвращает все данные, хранящиеся о пользователе.
    Используется для /mydata (пользователь) и /userinfo (admin).
    """
    async with async_session() as session:
        # Основная запись
        user_row = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_row.scalar_one_or_none()

        # Профиль
        profile_row = await session.execute(
            select(UserProfile).where(UserProfile.telegram_id == telegram_id)
        )
        profile = profile_row.scalar_one_or_none()

        # Количество опубликованных постов (только метрика, не контент)
        posts_count = await session.scalar(
            select(func.count(PublishedPost.id))
        )

    if not user:
        return {}

    today = date.today()
    daily = user.daily_requests if user.last_request_date == today else 0

    result: dict = {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "full_name": user.full_name,
        "is_pro": user.is_pro,
        "is_expert": user.is_expert,
        "pro_until": str(user.pro_until) if user.pro_until else None,
        "daily_requests": daily,
        "total_requests": user.total_requests,
        "interest": user.interest,
        "registered_at": str(user.created_at),
    }

    if profile:
        result["profile"] = {
            "age_group": profile.age_group,
            "gender": profile.gender,
            "audience_type": profile.audience_type,
            "language": profile.language,
            "branches": profile.branches,
            "updated_at": str(profile.updated_at),
        }

    return result


async def delete_user_data(telegram_id: int) -> bool:
    """
    Удаляет все персональные данные пользователя (GDPR / 152-ФЗ).
    Анонимизирует запись User (обнуляет username, full_name),
    удаляет UserProfile.
    Возвращает True если пользователь найден и данные удалены.
    """
    from sqlalchemy import delete as sa_delete

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return False

        # Анонимизируем User (сохраняем агрегаты для статистики)
        await session.execute(
            update(User).where(User.telegram_id == telegram_id).values(
                username=None,
                full_name=None,
                interest=None,
                is_pro=False,
                is_expert=False,
                pro_until=None,
                daily_requests=0,
                total_requests=0,
                last_request_date=None,
            )
        )

        # Удаляем профиль полностью
        await session.execute(
            sa_delete(UserProfile).where(UserProfile.telegram_id == telegram_id)
        )

        await session.commit()
    return True
