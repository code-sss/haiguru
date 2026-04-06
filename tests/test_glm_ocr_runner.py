"""Tests for glm_ocr/runner.py.

External dependencies (ollama, filesystem writes) are mocked so these tests
run without Ollama or GPU access.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from glm_ocr.runner import _strip_outer_code_fence, process_image


# ---------------------------------------------------------------------------
# _strip_outer_code_fence
# ---------------------------------------------------------------------------


class TestStripOuterCodeFence:
    def test_strips_markdown_fence(self):
        text = "```markdown\n### CONTENT\nSome text\n```"
        assert _strip_outer_code_fence(text) == "### CONTENT\nSome text"

    def test_strips_generic_fence(self):
        text = "```\n### CONTENT\nSome text\n```"
        assert _strip_outer_code_fence(text) == "### CONTENT\nSome text"

    def test_no_fence_returns_unchanged(self):
        text = "### CONTENT\nSome text"
        assert _strip_outer_code_fence(text) == "### CONTENT\nSome text"

    def test_strips_leading_trailing_whitespace(self):
        text = "  ```\ncontent\n```  "
        assert _strip_outer_code_fence(text) == "content"

    def test_preserves_inner_code_fences(self):
        text = "```markdown\n### CONTENT\n```python\ncode\n```\n\n```"
        # The outer fence is stripped; inner fences remain.
        # The blank line before the closing fence is included in the captured group.
        result = _strip_outer_code_fence(text)
        assert result == "### CONTENT\n```python\ncode\n```\n"

    def test_empty_string(self):
        assert _strip_outer_code_fence("") == ""


# ---------------------------------------------------------------------------
# process_image
# ---------------------------------------------------------------------------


def _make_fake_stream(*chunks):
    """Helper that yields OCR stream events."""
    yield ("__first_token__", 0.1)
    for chunk in chunks:
        yield ("chunk", chunk)
    yield ("__done__", 1.0)


@patch("glm_ocr.runner.check_quality", return_value=[])
@patch("glm_ocr.runner.save_raw_response")
@patch("glm_ocr.runner.send_streamed_request")
@patch("glm_ocr.runner.get_optimized_image_b64", return_value="base64data")
def test_process_image_success(mock_b64, mock_stream, mock_save, mock_quality, tmp_path):
    mock_stream.return_value = _make_fake_stream("### CONTENT\n", "Some theory text " * 20)
    expected_out = str(tmp_path / "raw_response_IMG_001.md")
    mock_save.return_value = expected_out

    result = process_image(
        img_path="/topic/inputs/IMG_001.jpg",
        model="test-model",
        folder_prompt="OCR this image",
        out_dir=str(tmp_path),
        overwrite=True,
    )

    assert result == expected_out
    mock_b64.assert_called_once_with("/topic/inputs/IMG_001.jpg")
    mock_stream.assert_called_once_with("test-model", "OCR this image", ["base64data"])
    mock_save.assert_called_once()
    # filename derived from image name
    saved_filename = mock_save.call_args[0][1]
    assert saved_filename == "raw_response_IMG_001.md"


@patch("glm_ocr.runner.get_optimized_image_b64", return_value="base64data")
def test_process_image_raises_when_no_prompt(mock_b64, tmp_path):
    with pytest.raises(FileNotFoundError, match="prompt"):
        process_image(
            img_path="/topic/inputs/IMG_001.jpg",
            model="test-model",
            folder_prompt=None,
            out_dir=str(tmp_path),
            overwrite=True,
        )


def test_process_image_skips_existing_without_overwrite(tmp_path):
    existing = tmp_path / "raw_response_IMG_001.md"
    existing.write_text("already done")

    result = process_image(
        img_path=str(tmp_path / "IMG_001.jpg"),
        model="test-model",
        folder_prompt="OCR this",
        out_dir=str(tmp_path),
        overwrite=False,
    )

    assert result == str(existing)


@patch("glm_ocr.runner.check_quality", return_value=["Missing '### CONTENT'"])
@patch("glm_ocr.runner.save_raw_response")
@patch("glm_ocr.runner.send_streamed_request")
@patch("glm_ocr.runner.get_optimized_image_b64", return_value="base64data")
def test_process_image_logs_quality_warnings(mock_b64, mock_stream, mock_save, mock_quality, tmp_path, capsys):
    mock_stream.return_value = _make_fake_stream("bad content")
    mock_save.return_value = str(tmp_path / "raw_response_IMG_001.md")

    process_image(
        img_path="/topic/inputs/IMG_001.jpg",
        model="test-model",
        folder_prompt="OCR this image",
        out_dir=str(tmp_path),
        overwrite=True,
    )

    captured = capsys.readouterr()
    assert "Quality warnings" in captured.out


@patch("glm_ocr.runner.check_quality", return_value=[])
@patch("glm_ocr.runner.save_raw_response")
@patch("glm_ocr.runner.send_streamed_request")
@patch("glm_ocr.runner.get_optimized_image_b64", return_value="base64data")
def test_process_image_concatenates_chunks(mock_b64, mock_stream, mock_save, mock_quality, tmp_path):
    mock_stream.return_value = _make_fake_stream("Hello ", "World")
    mock_save.return_value = str(tmp_path / "raw_response_IMG.md")

    process_image(
        img_path="/topic/inputs/IMG.jpg",
        model="m",
        folder_prompt="p",
        out_dir=str(tmp_path),
        overwrite=True,
    )

    saved_content = mock_save.call_args[0][2]  # third positional arg = content
    assert saved_content == "Hello World"
