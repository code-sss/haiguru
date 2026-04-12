"""Shared get-or-create helpers for DB upsert operations."""

from sqlalchemy.orm import Session

from db.models import Category, CoursePathNode, ExamTemplate, ExamTemplateQuestion, ParagraphQuestion, Question, Topic, TopicContent


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
        .filter_by(name=name, node_type=node_type, category_id=category_id, parent_id=parent_id)
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


def get_or_create_question(
    session: Session,
    topic_id,
    question_text: str,
    question_type: str,
    options: list,
    correct_answers: list,
) -> Question:
    obj = session.query(Question).filter_by(topic_id=topic_id, question_text=question_text).first()
    if obj:
        obj.question_type = question_type
        obj.options = options
        obj.correct_answers = correct_answers
        print(f"  Updated question: {question_text[:60]}")
    else:
        obj = Question(
            topic_id=topic_id,
            question_text=question_text,
            question_type=question_type,
            options=options,
            correct_answers=correct_answers,
        )
        session.add(obj)
        session.flush()
        print(f"  Created question: {question_text[:60]}")
    return obj


def get_or_create_exam_template(
    session: Session,
    course_node_id,
    title: str,
    description: str | None,
    mode: str,
    passing_score: float | None,
    duration_minutes: int | None,
    created_by,
) -> ExamTemplate:
    obj = session.query(ExamTemplate).filter_by(title=title, course_path_node_id=course_node_id).first()
    if obj:
        obj.description = description
        obj.mode = mode
        obj.passing_score = passing_score
        obj.duration_minutes = duration_minutes
        print(f"  Updated exam template: {title}")
    else:
        obj = ExamTemplate(
            course_path_node_id=course_node_id,
            title=title,
            description=description,
            mode=mode,
            passing_score=passing_score,
            duration_minutes=duration_minutes,
            created_by=created_by,
        )
        session.add(obj)
        session.flush()
        print(f"  Created exam template: {title}")
    return obj


def create_exam_template_question(
    session: Session,
    exam_template_id,
    question_id,
    paragraph_question_id,
    order: int,
    points: int,
) -> ExamTemplateQuestion:
    obj = ExamTemplateQuestion(
        exam_template_id=exam_template_id,
        question_id=question_id,
        paragraph_question_id=paragraph_question_id,
        order=order,
        points=points,
    )
    session.add(obj)
    session.flush()
    return obj


def get_or_create_paragraph_question(
    session: Session,
    content: str,
    title: str,
    topic_id,
    question_ids: list,
) -> ParagraphQuestion:
    obj = session.query(ParagraphQuestion).filter_by(topic_id=topic_id, content=content).first()
    if obj:
        obj.question_ids = question_ids
        print(f"  Updated paragraph question: {title}")
    else:
        obj = ParagraphQuestion(
            topic_id=topic_id,
            content=content,
            title=title,
            question_ids=question_ids,
        )
        session.add(obj)
        session.flush()
        print(f"  Created paragraph question: {title}")
    return obj
