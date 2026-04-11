"""DB read/write for eval_pipeline.

load_session()  — fetch ungraded ESQ rows for a completed session.
save_results()  — write grades back and recompute session score.
"""

from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import DATABASE_URL
from db.models import ExamSession, ExamSessionQuestion, Question


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SessionItem:
    esq: ExamSessionQuestion
    question: Question
    image_path: str | None  # set when user_answer starts with "image:"


@dataclass
class SessionData:
    session_id: uuid.UUID
    user_id: uuid.UUID
    items: list[SessionItem] = field(default_factory=list)


@dataclass
class QuestionResult:
    esq_id: uuid.UUID
    earned_points: float
    is_correct: bool | None
    user_answer: str | None  # non-None only when OCR replaced an "image:" prefix


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_session(session_id: uuid.UUID | str) -> SessionData:
    """Return ungraded items for a completed exam session.

    Raises:
        ValueError: session not found or not in 'completed' status.
    """
    sid = uuid.UUID(str(session_id))
    engine = create_engine(DATABASE_URL)

    with Session(engine) as db:
        session = db.get(ExamSession, sid)
        if session is None:
            raise ValueError(f"ExamSession {sid} not found")
        if session.status != "completed":
            raise ValueError(
                f"ExamSession {sid} has status '{session.status}', expected 'completed'"
            )

        esq_rows = (
            db.query(ExamSessionQuestion)
            .filter(
                ExamSessionQuestion.exam_session_id == sid,
                ExamSessionQuestion.earned_points.is_(None),
            )
            .all()
        )

        if not esq_rows:
            warnings.warn(f"No ungraded rows found for session {sid}")
            return SessionData(session_id=sid, user_id=session.user_id)

        # Bulk-fetch questions to avoid N+1
        question_ids = {row.question_id for row in esq_rows if row.question_id}
        questions = {
            q.id: q
            for q in db.query(Question).filter(Question.id.in_(question_ids)).all()
        }

        items: list[SessionItem] = []
        for esq in esq_rows:
            question = questions.get(esq.question_id)
            if question is None:
                warnings.warn(
                    f"Question {esq.question_id} not found for ESQ {esq.id} — skipping"
                )
                continue

            image_path: str | None = None
            if esq.user_answer and esq.user_answer.startswith("image:"):
                image_path = esq.user_answer[len("image:"):]

            items.append(SessionItem(esq=esq, question=question, image_path=image_path))

        # Detach objects so callers can use them outside this session
        db.expunge_all()

    return SessionData(session_id=sid, user_id=session.user_id, items=items)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_results(session_id: uuid.UUID | str, results: list[QuestionResult]) -> None:
    """Write grades back to DB and recompute the session's total score.

    Uses a single transaction. On failure the session auto-rolls back.
    Decision #1: always re-sums ALL earned_points for the session, making
    eval_pipeline the authoritative final scorer.
    """
    sid = uuid.UUID(str(session_id))
    engine = create_engine(DATABASE_URL)

    with Session(engine) as db:
        with db.begin():
            # 1. Write individual question results
            result_map = {r.esq_id: r for r in results}
            esq_rows = (
                db.query(ExamSessionQuestion)
                .filter(ExamSessionQuestion.exam_session_id == sid)
                .all()
            )

            for esq in esq_rows:
                result = result_map.get(esq.id)
                if result is None:
                    continue
                esq.earned_points = result.earned_points
                esq.is_correct = result.is_correct
                if result.user_answer is not None:
                    esq.user_answer = result.user_answer

            # 2. Re-sum ALL earned_points for this session
            total = sum(
                (row.earned_points or 0.0) for row in esq_rows
            )

            # 3. Overwrite session score
            session = db.get(ExamSession, sid)
            if session is None:
                raise ValueError(f"ExamSession {sid} not found during save")
            session.score = total
