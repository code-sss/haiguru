"""Load step: upsert topic hierarchy and content into Postgres."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Category, CoursePathNode, Topic, TopicContent
from .extract import TopicContext

DATABASE_URL = "postgresql://haiguru:haiguru_pass@localhost:5433/haiguru_db"


def _get_or_create_category(session: Session, name: str) -> Category:
    obj = session.query(Category).filter_by(name=name).first()
    if not obj:
        obj = Category(name=name, path_type="structured")
        session.add(obj)
        session.flush()
        print(f"  Created category: {name}")
    return obj


def _get_or_create_node(
    session: Session,
    name: str,
    node_type: str,
    category_id,
    parent_id=None,
) -> CoursePathNode:
    obj = (
        session.query(CoursePathNode)
        .filter_by(name=name, node_type=node_type, category_id=category_id)
        .first()
    )
    if not obj:
        obj = CoursePathNode(
            name=name,
            node_type=node_type,
            category_id=category_id,
            parent_id=parent_id,
        )
        session.add(obj)
        session.flush()
        print(f"  Created {node_type}: {name}")
    return obj


def _get_or_create_topic(session: Session, title: str, course_node_id) -> Topic:
    obj = session.query(Topic).filter_by(title=title, course_path_node_id=course_node_id).first()
    if not obj:
        obj = Topic(title=title, course_path_node_id=course_node_id)
        session.add(obj)
        session.flush()
        print(f"  Created topic: {title}")
    return obj


def _upsert_topic_content(session: Session, topic_id, title: str, text: str, order: int) -> None:
    obj = session.query(TopicContent).filter_by(topic_id=topic_id, title=title).first()
    if obj:
        obj.text = text
        obj.order = order
        print(f"  Updated content: {title}")
    else:
        obj = TopicContent(
            topic_id=topic_id,
            content_type="text",
            title=title,
            text=text,
            order=order,
        )
        session.add(obj)
        print(f"  Inserted content: {title}")


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
        category = _get_or_create_category(session, ctx.category_name)

        grade_node = _get_or_create_node(
            session, ctx.grade, "grade", category.id
        )
        subject_node = _get_or_create_node(
            session, ctx.subject, "subject", category.id, parent_id=grade_node.id
        )
        course_node = _get_or_create_node(
            session, ctx.volume, "course", category.id, parent_id=subject_node.id
        )
        topic = _get_or_create_topic(session, ctx.topic, course_node.id)

        # --- content pages ---
        for order, md_path in enumerate(md_files, start=1):
            text = md_path.read_text(encoding="utf-8").strip()
            if not text:
                print(f"  Skipping empty file: {md_path.name}")
                continue
            _upsert_topic_content(session, topic.id, title=md_path.name, text=text, order=order)

        session.commit()
        print(f"[Load] Done.")
