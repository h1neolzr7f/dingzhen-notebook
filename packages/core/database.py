"""SQLAlchemy tables and SQLite engine helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class PaperRow(Base):
    __tablename__ = "papers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    capture_status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    questions: Mapped[list["QuestionRow"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class QuestionRow(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    paper: Mapped[PaperRow] = relationship(back_populates="questions")


def make_engine(database: str | Path = "data/fenbi-study.db") -> Engine:
    value = str(database)
    if value == ":memory:" or value.startswith("sqlite:"):
        url = value if value.startswith("sqlite:") else "sqlite+pysqlite:///:memory:"
    else:
        path = Path(value).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+pysqlite:///{path.as_posix()}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)

