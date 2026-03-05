from datetime import date, datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, DateTime, Date, select, update
from config.settings import settings


class Base(DeclarativeBase):
    pass


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
    interest: Mapped[str] = mapped_column(String(32), nullable=True)  # tech/health/finance/psychology
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)


engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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

        # Pro/Expert users have no limit
        if user.is_pro or user.is_expert:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(total_requests=User.total_requests + 1)
            )
            await session.commit()
            return True

        # Reset daily counter if new day
        if user.last_request_date != today:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(daily_requests=1, last_request_date=today, total_requests=User.total_requests + 1)
            )
            await session.commit()
            return True

        # Check limit
        from config.settings import settings
        if user.daily_requests >= settings.FREE_DAILY_LIMIT:
            return False

        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
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
