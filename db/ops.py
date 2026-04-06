"""Shared get-or-create helpers for DB upsert operations."""

from sqlalchemy.orm import Session

from db.models import Category, CoursePathNode, Topic, TopicContent


def get_or_create_category(session: Session, name: str) -> Category:
    obj = session.query(Category).filter_by(name=name).first()
    if not obj:
        obj = Category(name=name, path_type="structured")
        session.add(obj)
        session.flush()
        print(f"  Created category: {name}")
    return obj


def get_or_create_node(
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


def get_or_create_topic(session: Session, title: str, course_node_id) -> Topic:
    obj = session.query(Topic).filter_by(title=title, course_path_node_id=course_node_id).first()
    if not obj:
        obj = Topic(title=title, course_path_node_id=course_node_id)
        session.add(obj)
        session.flush()
        print(f"  Created topic: {title}")
    return obj


def upsert_topic_content(session: Session, topic_id, title: str, text: str, order: int) -> None:
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
