"""SQLAlchemy table definitions for haiguru-backend."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Category & course hierarchy
# ---------------------------------------------------------------------------


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    path_type = Column(
        Enum("structured", "flexible", name="pathtype"),
        nullable=False,
        default="structured",
    )


class CoursePathNode(Base):
    __tablename__ = "course_path_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    node_type = Column(
        Enum("grade", "subject", "course", name="nodetype"),
        nullable=False,
    )
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    parent_id = Column(
        UUID(as_uuid=True), ForeignKey("course_path_nodes.id"), nullable=True
    )
    order = Column(Integer, nullable=True)
    owner_type = Column(String, nullable=False, default="platform")
    owner_id = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Topics & content
# ---------------------------------------------------------------------------


class Topic(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    course_path_node_id = Column(
        UUID(as_uuid=True), ForeignKey("course_path_nodes.id"), nullable=False
    )
    order = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="live")
    owner_type = Column(String, nullable=False, default="platform")
    owner_id = Column(String, nullable=True)


class TopicContent(Base):
    __tablename__ = "topic_contents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False)
    content_type = Column(
        Enum("video", "pdf", "text", "question", "question_answer", name="contenttype"),
        nullable=False,
    )
    title = Column(String, nullable=False)
    url = Column(String, nullable=True)
    text = Column(String, nullable=True)
    order = Column(Integer, nullable=False)
    description = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(String, nullable=False)
    question_type = Column(
        Enum(
            "single_choice",
            "multiple_choice",
            "true_false",
            "fill_in_the_blank",
            "essay",
            "paragraph",
            name="questiontype",
        ),
        nullable=False,
    )
    options = Column(JSONB, nullable=False, default=list)
    correct_answers = Column(JSONB, nullable=False, default=list)
    explanation = Column(String, nullable=True)
    difficulty = Column(
        Enum("easy", "medium", "hard", name="difficultylevel"),
        nullable=False,
        default="medium",
    )
    tags = Column(JSONB, nullable=True)
    image_url = Column(String, nullable=True)
    # which topic this question belongs to
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)


class ParagraphQuestion(Base):
    """A parent paragraph that groups sub-questions."""

    __tablename__ = "paragraph_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    passage = Column(String, nullable=False)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)


# ---------------------------------------------------------------------------
# Exam templates
# ---------------------------------------------------------------------------


class ExamTemplate(Base):
    __tablename__ = "exam_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_path_node_id = Column(
        UUID(as_uuid=True), ForeignKey("course_path_nodes.id"), nullable=False
    )
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    mode = Column(
        Enum("static", "dynamic", "custom", name="exammode"),
        nullable=False,
    )
    ruleset = Column(JSONB, nullable=True)
    created_by = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    duration_minutes = Column(Integer, nullable=True)
    passing_score = Column(Float, nullable=True)
    owner_type = Column(String, nullable=False, default="platform")
    owner_id = Column(String, nullable=True)
    organization_id = Column(String, nullable=True)
    purpose = Column(String, nullable=False, default="exam")

    __table_args__ = (
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="ck_exam_templates_duration_positive",
        ),
        CheckConstraint(
            "passing_score IS NULL OR (passing_score >= 0.0 AND passing_score <= 1.0)",
            name="ck_exam_templates_passing_score_range",
        ),
    )


class ExamTemplateQuestion(Base):
    __tablename__ = "exam_template_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_template_id = Column(
        UUID(as_uuid=True), ForeignKey("exam_templates.id"), nullable=True
    )
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=True)
    paragraph_question_id = Column(
        UUID(as_uuid=True), ForeignKey("paragraph_questions.id"), nullable=True
    )
    order = Column(Integer, nullable=True)
    points = Column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Exam sessions (user attempts)
# ---------------------------------------------------------------------------


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False)  # Keycloak sub
    exam_template_id = Column(
        UUID(as_uuid=True), ForeignKey("exam_templates.id"), nullable=True
    )
    course_path_node_id = Column(
        UUID(as_uuid=True), ForeignKey("course_path_nodes.id"), nullable=False
    )
    mode = Column(
        Enum("static", "dynamic", "custom", name="exammode"),
        nullable=False,
    )
    ruleset = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Float, nullable=True)
    status = Column(
        Enum("pending", "ongoing", "completed", "failed", name="examstatus"),
        nullable=True,
    )


class ExamSessionQuestion(Base):
    __tablename__ = "exam_session_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_session_id = Column(
        UUID(as_uuid=True), ForeignKey("exam_sessions.id"), nullable=True
    )
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=True)
    order = Column(Integer, nullable=True)
    points = Column(Integer, nullable=True)
    earned_points = Column(Float, nullable=True)


class Answer(Base):
    __tablename__ = "answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    user_id = Column(String, nullable=False)  # Keycloak sub
    session_id = Column(UUID(as_uuid=True), ForeignKey("exam_sessions.id"), nullable=False)
    selected_options = Column(ARRAY(String), nullable=True)
    text_answer = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
