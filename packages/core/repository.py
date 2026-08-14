"""Transactional SQLite repository with idempotent upserts."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine

from .database import Base, PaperRow, QuestionRow, make_engine, make_session_factory
from .integrity import transition_question
from .models import Paper, PipelineStatus, Question


class SQLiteRepository:
    def __init__(self, database: str | Path | Engine = "data/fenbi-study.db") -> None:
        self.engine = database if isinstance(database, Engine) else make_engine(database)
        self.sessions = make_session_factory(self.engine)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def upsert_paper(self, paper: Paper) -> Paper:
        paper.updated_at = paper.updated_at.now().astimezone()
        payload = paper.model_dump(mode="json")
        with self.sessions.begin() as session:
            row = session.get(PaperRow, paper.id)
            if row is None:
                session.add(PaperRow(id=paper.id, title=paper.title, capture_status=paper.capture_status.value,
                                     payload=payload, updated_at=paper.updated_at))
            else:
                row.title = paper.title
                row.capture_status = paper.capture_status.value
                row.payload = payload
                row.updated_at = paper.updated_at
        return paper

    def get_paper(self, paper_id: str) -> Paper | None:
        with self.sessions() as session:
            row = session.get(PaperRow, paper_id)
            return Paper.model_validate(row.payload) if row else None

    def list_papers(self) -> list[Paper]:
        with self.sessions() as session:
            rows = session.scalars(select(PaperRow).order_by(PaperRow.updated_at.desc())).all()
            return [Paper.model_validate(row.payload) for row in rows]

    def upsert_question(self, question: Question, *, assess: bool = True) -> Question:
        if assess:
            transition_question(question)
        payload = question.model_dump(mode="json")
        with self.sessions.begin() as session:
            if session.get(PaperRow, question.paper_id) is None:
                raise KeyError(f"paper does not exist: {question.paper_id}")
            row = session.get(QuestionRow, question.id)
            if row is None:
                session.add(QuestionRow(id=question.id, paper_id=question.paper_id,
                                        sequence=question.sequence,
                                        verification_status=question.verification_status.value,
                                        payload=payload))
            else:
                row.paper_id = question.paper_id
                row.sequence = question.sequence
                row.verification_status = question.verification_status.value
                row.payload = payload
        return question

    def get_question(self, question_id: str) -> Question | None:
        with self.sessions() as session:
            row = session.get(QuestionRow, question_id)
            return Question.model_validate(row.payload) if row else None

    def list_questions(
        self, paper_id: str, status: PipelineStatus | None = None
    ) -> list[Question]:
        statement = select(QuestionRow).where(QuestionRow.paper_id == paper_id)
        if status is not None:
            statement = statement.where(QuestionRow.verification_status == status.value)
        statement = statement.order_by(QuestionRow.sequence, QuestionRow.id)
        with self.sessions() as session:
            return [Question.model_validate(row.payload) for row in session.scalars(statement).all()]

    def review_queue(self, paper_id: str | None = None) -> list[Question]:
        statement = select(QuestionRow).where(
            QuestionRow.verification_status == PipelineStatus.NEEDS_REVIEW.value
        )
        if paper_id is not None:
            statement = statement.where(QuestionRow.paper_id == paper_id)
        statement = statement.order_by(QuestionRow.paper_id, QuestionRow.sequence)
        with self.sessions() as session:
            return [Question.model_validate(row.payload) for row in session.scalars(statement).all()]

    def delete_question(self, question_id: str) -> bool:
        with self.sessions.begin() as session:
            row = session.get(QuestionRow, question_id)
            if row is None:
                return False
            session.delete(row)
            return True
