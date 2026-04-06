"""Tests for etl_pipeline/extract.py."""

import pytest
from pathlib import Path

from etl_pipeline.extract import TopicContext, extract


def _make_topic_dir(base: Path, names=("SVC", "GRADE_7", "MATHEMATICS", "VOLUME_1", "INTEGERS")):
    """Create a minimal topic folder structure and return the topic path."""
    topic_dir = base.joinpath(*names)
    (topic_dir / "inputs").mkdir(parents=True)
    return topic_dir


class TestExtract:
    def test_happy_path_parses_hierarchy(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        ctx = extract(str(topic_dir))

        assert ctx.category_name == "SVC"
        assert ctx.grade == "GRADE_7"
        assert ctx.subject == "MATHEMATICS"
        assert ctx.volume == "VOLUME_1"
        assert ctx.topic == "INTEGERS"

    def test_returns_topic_context_instance(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        ctx = extract(str(topic_dir))
        assert isinstance(ctx, TopicContext)

    def test_topic_path_is_resolved(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        ctx = extract(str(topic_dir))
        assert ctx.topic_path == topic_dir.resolve()

    def test_outputs_dir_set_correctly(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        ctx = extract(str(topic_dir))
        assert ctx.outputs_dir == topic_dir.resolve() / "outputs"

    def test_image_paths_empty_when_no_images(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        ctx = extract(str(topic_dir))
        assert ctx.image_paths == []

    def test_image_paths_populated_with_jpg(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path)
        (topic_dir / "inputs" / "IMG_001.jpg").write_bytes(b"fake")
        (topic_dir / "inputs" / "IMG_002.jpg").write_bytes(b"fake")
        ctx = extract(str(topic_dir))
        assert len(ctx.image_paths) == 2

    def test_raises_for_nonexistent_path(self):
        with pytest.raises(ValueError, match="does not exist"):
            extract("/nonexistent/path/that/does/not/exist/at/all")

    def test_raises_for_file_not_directory(self, tmp_path):
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")
        with pytest.raises(ValueError, match="does not exist or is not a directory"):
            extract(str(file_path))

    def test_different_category_names_parsed(self, tmp_path):
        topic_dir = _make_topic_dir(tmp_path, ("NATIONAL", "GRADE_10", "PHYSICS", "TERM_1", "MOTION"))
        ctx = extract(str(topic_dir))
        assert ctx.category_name == "NATIONAL"
        assert ctx.grade == "GRADE_10"
        assert ctx.subject == "PHYSICS"
        assert ctx.volume == "TERM_1"
        assert ctx.topic == "MOTION"
