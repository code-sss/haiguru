"""Tests for db/ops.py — exercises get-or-create helpers using a mock Session.

No database connection is required; the SQLAlchemy Session is replaced with a
MagicMock whose query chain returns controlled values.
"""

import uuid
import pytest
from unittest.mock import MagicMock, call

from db.models import Category, CoursePathNode, Topic, TopicContent
from db.ops import (
    get_or_create_category,
    get_or_create_node,
    get_or_create_topic,
    upsert_topic_content,
)


def _mock_session(found=None):
    """Return a MagicMock session whose query().filter_by().first() returns `found`."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = found
    return session


# ---------------------------------------------------------------------------
# get_or_create_category
# ---------------------------------------------------------------------------


class TestGetOrCreateCategory:
    def test_returns_existing_without_side_effects(self):
        existing = Category(name="SVC", path_type="structured")
        session = _mock_session(found=existing)

        result = get_or_create_category(session, "SVC")

        assert result is existing
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_creates_new_category_when_not_found(self):
        session = _mock_session(found=None)

        result = get_or_create_category(session, "SVC")

        assert result.name == "SVC"
        assert result.path_type == "structured"
        session.add.assert_called_once_with(result)
        session.flush.assert_called_once()

    def test_queries_by_name(self):
        session = _mock_session(found=None)
        get_or_create_category(session, "MY_CATEGORY")
        session.query.assert_called_with(Category)
        session.query.return_value.filter_by.assert_called_with(name="MY_CATEGORY")


# ---------------------------------------------------------------------------
# get_or_create_node
# ---------------------------------------------------------------------------


class TestGetOrCreateNode:
    def test_returns_existing_node(self):
        cat_id = uuid.uuid4()
        existing = CoursePathNode(name="GRADE_7", node_type="grade", category_id=cat_id)
        session = _mock_session(found=existing)

        result = get_or_create_node(session, "GRADE_7", "grade", cat_id)

        assert result is existing
        session.add.assert_not_called()

    def test_creates_new_node_without_parent(self):
        cat_id = uuid.uuid4()
        session = _mock_session(found=None)

        result = get_or_create_node(session, "GRADE_7", "grade", cat_id)

        assert result.name == "GRADE_7"
        assert result.node_type == "grade"
        assert result.category_id == cat_id
        assert result.parent_id is None
        session.add.assert_called_once_with(result)
        session.flush.assert_called_once()

    def test_creates_new_node_with_parent(self):
        cat_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        session = _mock_session(found=None)

        result = get_or_create_node(session, "MATHEMATICS", "subject", cat_id, parent_id=parent_id)

        assert result.parent_id == parent_id
        session.add.assert_called_once()

    def test_queries_with_correct_filters(self):
        cat_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        session = _mock_session(found=None)

        get_or_create_node(session, "MATHEMATICS", "subject", cat_id, parent_id=parent_id)

        session.query.return_value.filter_by.assert_called_with(
            name="MATHEMATICS",
            node_type="subject",
            category_id=cat_id,
            parent_id=parent_id,
        )


# ---------------------------------------------------------------------------
# get_or_create_topic
# ---------------------------------------------------------------------------


class TestGetOrCreateTopic:
    def test_returns_existing_topic(self):
        node_id = uuid.uuid4()
        existing = Topic(title="INTEGERS", course_path_node_id=node_id)
        session = _mock_session(found=existing)

        result = get_or_create_topic(session, "INTEGERS", node_id)

        assert result is existing
        session.add.assert_not_called()

    def test_creates_new_topic(self):
        node_id = uuid.uuid4()
        session = _mock_session(found=None)

        result = get_or_create_topic(session, "INTEGERS", node_id)

        assert result.title == "INTEGERS"
        assert result.course_path_node_id == node_id
        session.add.assert_called_once_with(result)
        session.flush.assert_called_once()

    def test_queries_by_title_and_node(self):
        node_id = uuid.uuid4()
        session = _mock_session(found=None)

        get_or_create_topic(session, "FRACTIONS", node_id)

        session.query.return_value.filter_by.assert_called_with(
            title="FRACTIONS",
            course_path_node_id=node_id,
        )


# ---------------------------------------------------------------------------
# upsert_topic_content
# ---------------------------------------------------------------------------


class TestUpsertTopicContent:
    def test_updates_text_and_order_on_existing_content(self):
        topic_id = uuid.uuid4()
        existing = TopicContent(
            topic_id=topic_id,
            content_type="text",
            title="raw_response_IMG_001.md",
            text="old text",
            order=1,
        )
        session = _mock_session(found=existing)

        upsert_topic_content(session, topic_id, "raw_response_IMG_001.md", "new text", 2)

        assert existing.text == "new text"
        assert existing.order == 2
        session.add.assert_not_called()

    def test_inserts_new_content_when_not_found(self):
        topic_id = uuid.uuid4()
        session = _mock_session(found=None)

        upsert_topic_content(session, topic_id, "raw_response_IMG_001.md", "some text", 1)

        session.add.assert_called_once()
        added: TopicContent = session.add.call_args[0][0]
        assert added.title == "raw_response_IMG_001.md"
        assert added.text == "some text"
        assert added.order == 1
        assert added.content_type == "text"
        assert added.topic_id == topic_id

    def test_queries_by_topic_id_and_title(self):
        topic_id = uuid.uuid4()
        session = _mock_session(found=None)

        upsert_topic_content(session, topic_id, "page1.md", "content", 3)

        session.query.return_value.filter_by.assert_called_with(
            topic_id=topic_id,
            title="page1.md",
        )
