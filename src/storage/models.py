from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str | None] = mapped_column(Text)

    default_mode: Mapped[str | None] = mapped_column(Text)
    default_style: Mapped[str | None] = mapped_column(Text)
    target_lang: Mapped[str] = mapped_column(Text, default="en")
    llm_model: Mapped[str | None] = mapped_column(Text)

    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_voice_seconds: Mapped[int] = mapped_column(Integer, default=0)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    history: Mapped[list["RequestHistory"]] = relationship(back_populates="user")


class RequestHistory(Base):
    __tablename__ = "request_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    mode: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(Text, nullable=False)

    input_type: Mapped[str] = mapped_column(Text, nullable=False)
    input_length: Mapped[int | None] = mapped_column(Integer)
    input_preview: Mapped[str | None] = mapped_column(Text)

    output_text: Mapped[str | None] = mapped_column(Text)
    output_length: Mapped[int | None] = mapped_column(Integer)

    llm_model: Mapped[str | None] = mapped_column(Text)
    transcription_ms: Mapped[int | None] = mapped_column(Integer)
    llm_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)

    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="history")


class TranscriptionCache(Base):
    __tablename__ = "transcription_cache"

    file_id: Mapped[str] = mapped_column(Text, primary_key=True)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillIndex(Base):
    __tablename__ = "skills_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_repo: Mapped[str] = mapped_column(Text, nullable=False)
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
