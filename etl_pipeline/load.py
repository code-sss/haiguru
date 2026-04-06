"""Load step: upsert topic hierarchy and content into Postgres."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import DATABASE_URL
from db.ops import get_or_create_category, get_or_create_node, get_or_create_topic, upsert_topic_content
from .extract import TopicContext


def load(ctx: TopicContext) -> None:
    """Upsert the full hierarchy and topic_content rows for a TopicContext."""

    md_files = sorted(ctx.outputs_dir.glob("raw_response_*.md"))
    if not md_files:
        print(f"[Load] No .md files found in {ctx.outputs_dir}, skipping.")
        return

    print(f"\n[Load] {ctx.topic} — {len(md_files)} page(s)")

    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        # --- hierarchy ---
        category = get_or_create_category(session, ctx.category_name)

        grade_node = get_or_create_node(
            session, ctx.grade, "grade", category.id
        )
        subject_node = get_or_create_node(
            session, ctx.subject, "subject", category.id, parent_id=grade_node.id
        )
        course_node = get_or_create_node(
            session, ctx.volume, "course", category.id, parent_id=subject_node.id
        )
        topic = get_or_create_topic(session, ctx.topic, course_node.id)

        # --- content pages ---
        for order, md_path in enumerate(md_files, start=1):
            text = md_path.read_text(encoding="utf-8").strip()
            if not text:
                print(f"  Skipping empty file: {md_path.name}")
                continue
            upsert_topic_content(session, topic.id, title=md_path.name, text=text, order=order)

        session.commit()
        print(f"[Load] Done.")
