"""Load step: upsert topic hierarchy and content into Postgres."""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import DATABASE_URL
from db.models import ExamTemplateQuestion
from db.ops import (
    create_exam_template_question,
    get_or_create_category,
    get_or_create_exam_template,
    get_or_create_node,
    get_or_create_paragraph_question,
    get_or_create_question,
    get_or_create_topic,
    upsert_topic_content,
)
from .extract import TopicContext
from .transform import TransformResult

# Default created_by UUID used when loading via CLI without an authenticated user.
_SYSTEM_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _build_topic(session: Session, ctx: TopicContext):
    """Get or create the full course hierarchy and return the Topic object."""
    category = get_or_create_category(session, ctx.category_name)
    grade_node = get_or_create_node(session, ctx.grade, "grade", category.id)
    subject_node = get_or_create_node(
        session, ctx.subject, "subject", category.id, parent_id=grade_node.id
    )
    course_node = get_or_create_node(
        session, ctx.volume, "course", category.id, parent_id=subject_node.id
    )
    return get_or_create_topic(session, ctx.topic, course_node.id)


def _load_contents(session: Session, ctx: TopicContext, topic, items: list[dict]) -> None:
    """Upsert topic_content rows from pre-transformed content dicts."""
    if not items:
        print(f"[Load] No content items for {ctx.topic}, skipping contents.")
        return

    print(f"[Load] {ctx.topic} — {len(items)} content page(s)")
    for item in items:
        upsert_topic_content(session, topic.id, title=item["title"], text=item["text"], order=item["order"])


def _load_exercises(session: Session, ctx: TopicContext, topic, items: list[dict]) -> None:
    """Upsert Question and ParagraphQuestion rows from pre-parsed question dicts."""
    if not items:
        print(f"[Load] No exercise items for {ctx.topic}, skipping exercises.")
        return

    print(f"[Load] {ctx.topic} — {len(items)} question(s)")

    # Maintain insertion order of passages across all items.
    paragraph_groups: dict[str, dict] = {}  # passage text → {title, ids}

    for q in items:
        q_obj = get_or_create_question(
            session,
            topic_id=topic.id,
            question_text=q["question_text"],
            question_type=q["question_type"],
            options=q["options"],
            correct_answers=q["correct_answers"],
        )
        if q.get("passage") is not None:
            passage = q["passage"]
            if passage not in paragraph_groups:
                title = q.get("paragraph_title") or passage[:60]
                paragraph_groups[passage] = {"title": title, "ids": []}
            paragraph_groups[passage]["ids"].append(q_obj.id)

    for passage, group in paragraph_groups.items():
        get_or_create_paragraph_question(
            session,
            content=passage,
            title=group["title"],
            topic_id=topic.id,
            question_ids=group["ids"],
        )


def load_json_exercises(
    result: TransformResult,
    created_by=None,
    ctx: TopicContext | None = None,
    course_node_id=None,
    topic_id=None,
) -> None:
    """Load a JSON exercises TransformResult: questions, paragraph_questions,
    exam_template, and exam_template_questions.

    Supply either ctx (derives course_node_id + topic_id from the topic path)
    or course_node_id directly (with optional topic_id).
    """
    effective_created_by = created_by or _SYSTEM_UUID
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        # Resolve course node and topic from ctx if provided
        resolved_course_node_id = course_node_id
        resolved_topic_id = topic_id
        if ctx is not None:
            topic = _build_topic(session, ctx)
            resolved_topic_id = topic.id
            resolved_course_node_id = topic.course_path_node_id

        print(f"\n[Load] {len(result.items)} question(s) from JSON")

        # Create questions, tracking order and paragraph membership
        question_objs: list[tuple] = []  # (Question, item_dict)
        paragraph_groups: dict[str, dict] = {}  # passage → {title, ids}

        for q in result.items:
            q_obj = get_or_create_question(
                session,
                topic_id=resolved_topic_id,
                question_text=q["question_text"],
                question_type=q["question_type"],
                options=q["options"],
                correct_answers=q["correct_answers"],
            )
            question_objs.append((q_obj, q))

            if q.get("passage") is not None:
                passage = q["passage"]
                if passage not in paragraph_groups:
                    title = q.get("paragraph_title") or passage[:60]
                    paragraph_groups[passage] = {"title": title, "ids": []}
                paragraph_groups[passage]["ids"].append(q_obj.id)

        # Create paragraph_questions, map passage text → paragraph_question id
        passage_to_pq_id: dict[str, uuid.UUID] = {}
        for passage, group in paragraph_groups.items():
            pq_obj = get_or_create_paragraph_question(
                session,
                content=passage,
                title=group["title"],
                topic_id=resolved_topic_id,
                question_ids=group["ids"],
            )
            passage_to_pq_id[passage] = pq_obj.id

        # Create exam template from top-level JSON metadata
        meta = result.exam_template_meta or {}
        exam_tmpl = get_or_create_exam_template(
            session,
            course_node_id=resolved_course_node_id,
            title=meta.get("title", "Untitled Exam"),
            description=meta.get("description"),
            mode=meta.get("mode", "static"),
            passing_score=meta.get("passing_score"),
            duration_minutes=meta.get("duration_minutes"),
            created_by=effective_created_by,
        )

        # Clear stale exam_template_questions before re-inserting
        session.query(ExamTemplateQuestion).filter_by(exam_template_id=exam_tmpl.id).delete()
        session.flush()

        for order, (q_obj, q_dict) in enumerate(question_objs, start=1):
            pq_id = passage_to_pq_id.get(q_dict.get("passage")) if q_dict.get("passage") else None
            create_exam_template_question(
                session,
                exam_template_id=exam_tmpl.id,
                question_id=q_obj.id,
                paragraph_question_id=pq_id,
                order=order,
                points=q_dict.get("points", 1),
            )

        session.commit()
        print("[Load] Done.")


def load(ctx: TopicContext, result: TransformResult) -> None:
    """Upsert the full hierarchy and content rows for one TransformResult.

    Call once per content_type. For 'both', __main__.py calls this twice.
    """
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        topic = _build_topic(session, ctx)

        if result.content_type == "contents":
            _load_contents(session, ctx, topic, result.items)
        elif result.content_type == "exercises":
            _load_exercises(session, ctx, topic, result.items)

        session.commit()
        print("[Load] Done.")

