"""Load step: upsert topic hierarchy and content into Postgres."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import DATABASE_URL
from db.ops import (
    get_or_create_category,
    get_or_create_node,
    get_or_create_paragraph_question,
    get_or_create_question,
    get_or_create_topic,
    upsert_topic_content,
)
from .extract import TopicContext
from .parse_exercises import parse_exercises_file


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


def _load_contents(session: Session, ctx: TopicContext, topic) -> None:
    """Upsert topic_content rows from outputs/contents_outputs/."""
    contents_dir = ctx.outputs_dir / "contents_outputs"
    md_files = sorted(contents_dir.glob("raw_response_*.md")) if contents_dir.is_dir() else []
    if not md_files:
        print(f"[Load] No .md files found in {contents_dir}, skipping contents.")
        return

    print(f"[Load] {ctx.topic} — {len(md_files)} content page(s)")
    for order, md_path in enumerate(md_files, start=1):
        text = md_path.read_text(encoding="utf-8").strip()
        if not text:
            print(f"  Skipping empty file: {md_path.name}")
            continue
        upsert_topic_content(session, topic.id, title=md_path.name, text=text, order=order)


def _load_exercises(session: Session, ctx: TopicContext, topic) -> None:
    """Parse exercise outputs and upsert Question/ParagraphQuestion rows."""
    exercises_dir = ctx.outputs_dir / "exercises_outputs"
    md_files = sorted(exercises_dir.glob("raw_response_*.md")) if exercises_dir.is_dir() else []
    if not md_files:
        print(f"[Load] No .md files found in {exercises_dir}, skipping exercises.")
        return

    print(f"[Load] {ctx.topic} — {len(md_files)} exercise file(s)")
    for md_path in md_files:
        questions = parse_exercises_file(md_path)
        if not questions:
            continue

        # Maintain insertion order of passages across this file.
        paragraph_groups: dict[str, list] = {}

        for q in questions:
            q_obj = get_or_create_question(
                session,
                topic_id=topic.id,
                question_text=q["question_text"],
                question_type=q["question_type"],
                options=q["options"],
                correct_answers=q["correct_answers"],
            )
            if q["passage"] is not None:
                passage = q["passage"]
                if passage not in paragraph_groups:
                    paragraph_groups[passage] = []
                paragraph_groups[passage].append(q_obj.id)

        for passage, question_ids in paragraph_groups.items():
            get_or_create_paragraph_question(
                session,
                passage=passage,
                topic_id=topic.id,
                question_ids=question_ids,
            )


def load(ctx: TopicContext, content_type: str = "contents") -> None:
    """Upsert the full hierarchy and content rows for a TopicContext.

    content_type: "contents" | "exercises" | "both"
    """
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        topic = _build_topic(session, ctx)

        if content_type in ("contents", "both"):
            _load_contents(session, ctx, topic)

        if content_type in ("exercises", "both"):
            _load_exercises(session, ctx, topic)

        session.commit()
        print("[Load] Done.")

