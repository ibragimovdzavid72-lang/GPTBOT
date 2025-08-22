from __future__ import annotations
from typing import Optional, List, Dict
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, Date, DateTime, ForeignKey, select, func

from settings import DATABASE_URL

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(16), default="chat")
    active_session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    daily_msgs: Mapped[int] = mapped_column(Integer, default=0)
    daily_imgs: Mapped[int] = mapped_column(Integer, default=0)
    last_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120), default="Диалог")
    system_prompt: Mapped[str] = mapped_column(String(4096), default="Ты умный, лаконичный ассистент.")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String(16000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    chat_id: Mapped[int] = mapped_column()
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    task: Mapped[str] = mapped_column(String(2000))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///./local.db"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Helpers
from sqlalchemy import select

async def upsert_user(session: AsyncSession, telegram_id: int, username: Optional[str]):
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    u = res.scalar_one_or_none()
    if not u:
        u = User(telegram_id=telegram_id, username=username)
        session.add(u)
        await session.flush()
        s = Session(user_id=u.id)
        session.add(s); await session.flush()
        u.active_session_id = s.id
    return u

async def get_active_session(session: AsyncSession, user: User) -> Session:
    if not user.active_session_id:
        s = Session(user_id=user.id); session.add(s); await session.flush(); user.active_session_id = s.id
    res = await session.execute(select(Session).where(Session.id == user.active_session_id))
    return res.scalar_one()

async def append_message(session: AsyncSession, session_id: int, role: str, content: str):
    session.add(Message(session_id=session_id, role=role, content=content[:16000]))

async def get_history(session: AsyncSession, session_id: int, limit: int) -> List[Dict[str,str]]:
    res = await session.execute(select(Message).where(Message.session_id==session_id).order_by(Message.id.desc()).limit(limit))
    rows = list(reversed(res.scalars().all()))
    return [{"role": r.role, "content": r.content} for r in rows]

async def set_mode(session: AsyncSession, user: User, mode: str):
    user.mode = mode

from datetime import date
async def inc_limits(session: AsyncSession, user: User, *, is_image: bool) -> Dict[str,int]:
    today = date.today()
    if user.last_date != today:
        user.daily_msgs = 0; user.daily_imgs = 0; user.last_date = today
    if is_image: user.daily_imgs += 1
    else: user.daily_msgs += 1
    return {"daily_msgs": user.daily_msgs, "daily_imgs": user.daily_imgs}

async def add_reminder(session: AsyncSession, user_id: int, chat_id: int, when, task: str):
    session.add(Reminder(user_id=user_id, chat_id=chat_id, remind_at=when, task=task))

async def due_reminders(session: AsyncSession):
    res = await session.execute(select(Reminder).where(Reminder.done==False, Reminder.remind_at <= func.now()))
    return res.scalars().all()

async def mark_reminder_done(session: AsyncSession, rid: int):
    res = await session.execute(select(Reminder).where(Reminder.id==rid))
    r = res.scalar_one_or_none()
    if r: r.done = True
