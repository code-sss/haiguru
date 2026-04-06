"""Tests for glm_ocr/utils.py — pure functions only, no external services."""

import os
import pytest

from glm_ocr.utils import check_quality, list_image_files, read_prompt_file


# ---------------------------------------------------------------------------
# check_quality
# ---------------------------------------------------------------------------

LONG_CONTENT = "A" * 200  # enough to pass the length heuristic


class TestCheckQuality:
    def test_returns_empty_list_for_valid_response(self):
        response = f"### CONTENT\n{LONG_CONTENT}"
        warnings = check_quality(response)
        assert warnings == []

    def test_missing_content_header(self):
        warnings = check_quality("Some text without the section header")
        assert any("### CONTENT" in w for w in warnings)

    def test_content_too_short(self):
        response = "### CONTENT\nTiny"  # only 4 chars after the header
        warnings = check_quality(response)
        assert any("short" in w.lower() for w in warnings)

    def test_q_number_pattern_triggers_warning(self):
        response = f"### CONTENT\n{LONG_CONTENT}\nQ. 1 What is photosynthesis?"
        warnings = check_quality(response)
        assert any("Q." in w for w in warnings)

    def test_numbered_question_pattern_triggers_warning(self):
        response = f"### CONTENT\n{LONG_CONTENT}\n1. What colour is the sky?"
        warnings = check_quality(response)
        assert any("?" in w for w in warnings)

    def test_mcq_option_pattern_triggers_warning(self):
        response = f"### CONTENT\n{LONG_CONTENT}\n(a) Option A\n(b) Option B"
        warnings = check_quality(response)
        assert any("(a)" in w.lower() or "option" in w.lower() for w in warnings)

    def test_multiple_warnings_returned(self):
        # No header + short content → at least 2 warnings
        warnings = check_quality("tiny")
        assert len(warnings) >= 2

    def test_returns_list(self):
        warnings = check_quality("")
        assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# read_prompt_file
# ---------------------------------------------------------------------------


class TestReadPromptFile:
    def test_reads_prompt_md(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "prompt.md").write_text("Describe the image.", encoding="utf-8")

        result = read_prompt_file(str(tmp_path))
        assert result == "Describe the image."

    def test_reads_prompt_txt_when_no_md(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "prompt.txt").write_text("OCR this page.", encoding="utf-8")

        result = read_prompt_file(str(tmp_path))
        assert result == "OCR this page."

    def test_prefers_prompt_md_over_txt(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "prompt.md").write_text("from md", encoding="utf-8")
        (prompts_dir / "prompt.txt").write_text("from txt", encoding="utf-8")

        result = read_prompt_file(str(tmp_path))
        assert result == "from md"

    def test_returns_none_when_no_prompt(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        result = read_prompt_file(str(tmp_path))
        assert result is None

    def test_returns_none_when_prompts_dir_missing(self, tmp_path):
        result = read_prompt_file(str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# list_image_files
# ---------------------------------------------------------------------------


class TestListImageFiles:
    def _make_inputs(self, tmp_path, filenames):
        inputs_dir = tmp_path / "inputs"
        inputs_dir.mkdir()
        for name in filenames:
            (inputs_dir / name).write_bytes(b"fake")
        return inputs_dir

    def test_yields_jpg_files(self, tmp_path):
        self._make_inputs(tmp_path, ["IMG_001.jpg", "IMG_002.jpg"])
        result = list(list_image_files(str(tmp_path)))
        assert len(result) == 2
        assert all(f.endswith(".jpg") for f in result)

    def test_recognises_all_supported_extensions(self, tmp_path):
        names = ["a.jpg", "b.jpeg", "c.png", "d.webp", "e.bmp", "f.tiff"]
        self._make_inputs(tmp_path, names)
        result = list(list_image_files(str(tmp_path)))
        assert len(result) == len(names)

    def test_skips_non_image_files(self, tmp_path):
        self._make_inputs(tmp_path, ["IMG_001.jpg", "notes.txt", "data.csv"])
        result = list(list_image_files(str(tmp_path)))
        assert len(result) == 1
        assert result[0].endswith("IMG_001.jpg")

    def test_returns_sorted_order(self, tmp_path):
        self._make_inputs(tmp_path, ["IMG_003.jpg", "IMG_001.jpg", "IMG_002.jpg"])
        result = list(list_image_files(str(tmp_path)))
        basenames = [os.path.basename(p) for p in result]
        assert basenames == sorted(basenames)

    def test_empty_inputs_yields_nothing(self, tmp_path):
        (tmp_path / "inputs").mkdir()
        result = list(list_image_files(str(tmp_path)))
        assert result == []

    def test_ignores_subdirectories(self, tmp_path):
        inputs_dir = tmp_path / "inputs"
        inputs_dir.mkdir()
        (inputs_dir / "subdir").mkdir()  # directory inside inputs/
        (inputs_dir / "IMG_001.jpg").write_bytes(b"fake")
        result = list(list_image_files(str(tmp_path)))
        assert len(result) == 1
