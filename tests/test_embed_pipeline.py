"""Tests for embed_pipeline/__main__.py — build_nodes() is a pure function."""

import uuid
import pytest

from embed_pipeline.__main__ import build_nodes


class _FakeRow:
    """Minimal stand-in for a SQLAlchemy row returned by CONTENT_QUERY."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _make_row(**overrides):
    defaults = dict(
        content_id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        topic_title="INTEGERS",
        course_name="VOLUME_1",
        subject_name="MATHEMATICS",
        grade_name="GRADE_7",
        category_name="SVC",
        text="The integer is a whole number.",
        order=1,
    )
    defaults.update(overrides)
    return _FakeRow(**defaults)


class TestBuildNodes:
    def test_empty_input_returns_empty_list(self):
        assert build_nodes([]) == []

    def test_creates_one_node_per_row(self):
        rows = [_make_row(), _make_row()]
        nodes = build_nodes(rows)
        assert len(nodes) == 2

    def test_node_text_matches_row_text(self):
        row = _make_row(text="Integers are whole numbers including negatives.")
        nodes = build_nodes([row])
        assert nodes[0].text == "Integers are whole numbers including negatives."

    def test_node_id_is_string_of_content_id(self):
        content_id = uuid.uuid4()
        row = _make_row(content_id=content_id)
        nodes = build_nodes([row])
        assert nodes[0].id_ == str(content_id)

    def test_metadata_topic_content_id(self):
        content_id = uuid.uuid4()
        row = _make_row(content_id=content_id)
        meta = build_nodes([row])[0].metadata
        assert meta["topic_content_id"] == str(content_id)

    def test_metadata_topic_id(self):
        topic_id = uuid.uuid4()
        row = _make_row(topic_id=topic_id)
        meta = build_nodes([row])[0].metadata
        assert meta["topic_id"] == str(topic_id)

    def test_metadata_hierarchy_fields(self):
        row = _make_row(
            topic_title="FRACTIONS",
            course_name="VOLUME_2",
            subject_name="SCIENCE",
            grade_name="GRADE_8",
            category_name="NATIONAL",
        )
        meta = build_nodes([row])[0].metadata
        assert meta["topic_title"] == "FRACTIONS"
        assert meta["course"] == "VOLUME_2"
        assert meta["subject"] == "SCIENCE"
        assert meta["grade"] == "GRADE_8"
        assert meta["category"] == "NATIONAL"

    def test_metadata_page_order(self):
        row = _make_row(order=5)
        meta = build_nodes([row])[0].metadata
        assert meta["page_order"] == 5

    def test_nodes_preserve_row_order(self):
        rows = [_make_row(text=f"page {i}") for i in range(1, 6)]
        nodes = build_nodes(rows)
        for i, node in enumerate(nodes):
            assert node.text == f"page {i + 1}"
