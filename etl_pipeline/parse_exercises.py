"""Parse structured exercises markdown files into question dicts."""

import re
import warnings
from pathlib import Path

_OPTION_RE = re.compile(r"^\(([a-z])\)\s+(.*)", re.IGNORECASE)
_ANSWER_LETTER_RE = re.compile(r"^\(([a-z])\)$", re.IGNORECASE)


def _letter_to_index(letter: str) -> int:
    return ord(letter.lower()) - ord("a")


def _extract_passage(block: str) -> str | None:
    """Extract the passage text from a ### PARAGRAPH block (supports multi-line)."""
    passage_lines = []
    in_passage = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("Passage:"):
            passage_lines.append(stripped[len("Passage:"):].strip())
            in_passage = True
        elif in_passage and stripped:
            passage_lines.append(stripped)
    return " ".join(passage_lines).strip() if passage_lines else None


def _parse_question_block(block: str, current_passage: str | None) -> dict | None:
    """Parse a single ### QUESTION block into a question dict."""
    question_type = None
    question_text_lines: list[str] = []
    options: list[str] = []
    answer_raw = None
    in_text = False

    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("Type:"):
            in_text = False
            question_type = stripped[len("Type:"):].strip()
        elif stripped.startswith("Text:"):
            in_text = True
            question_text_lines = [stripped[len("Text:"):].strip()]
        elif stripped.startswith("Answer:"):
            in_text = False
            answer_raw = stripped[len("Answer:"):].strip()
        else:
            m = _OPTION_RE.match(stripped)
            if m:
                in_text = False
                options.append(m.group(2).strip())
            elif in_text and stripped:
                question_text_lines.append(stripped)

    question_text = " ".join(question_text_lines).strip() if question_text_lines else None

    if not question_type or not question_text:
        return None

    # Resolve letter-based answers to option text
    correct_answers: list[str] = []
    if answer_raw:
        for part in re.split(r",\s*", answer_raw):
            part = part.strip()
            m = _ANSWER_LETTER_RE.match(part)
            if m:
                idx = _letter_to_index(m.group(1))
                if 0 <= idx < len(options):
                    correct_answers.append(options[idx])
                else:
                    correct_answers.append(part)
            else:
                correct_answers.append(part)

    return {
        "question_type": question_type,
        "question_text": question_text,
        "options": options,
        "correct_answers": correct_answers,
        "passage": current_passage,
    }


def parse_exercises_file(md_path: Path) -> list[dict]:
    """Parse a single exercises markdown file into a list of question dicts.

    Each dict has keys: question_type, question_text, options, correct_answers, passage.
    passage is None for standalone questions; a string for paragraph sub-questions.
    Returns an empty list (with a warning) if no ### QUESTION markers are found.
    """
    text = md_path.read_text(encoding="utf-8")

    if "### QUESTION" not in text:
        warnings.warn(
            f"[parse_exercises] No ### QUESTION markers in {md_path.name}, skipping.",
            stacklevel=2,
        )
        return []

    # Split by section markers, keeping the markers as separate elements.
    # Result: [preamble, marker1, block1, marker2, block2, ...]
    sections = re.split(r"(###\s+(?:QUESTION|PARAGRAPH))", text)

    results: list[dict] = []
    current_passage: str | None = None

    # Markers are at odd indices; their content blocks follow at even indices.
    i = 1
    while i < len(sections) - 1:
        marker = sections[i].strip()
        content = sections[i + 1]
        i += 2

        if re.match(r"###\s+PARAGRAPH", marker):
            current_passage = _extract_passage(content)
        elif re.match(r"###\s+QUESTION", marker):
            q = _parse_question_block(content, current_passage)
            if q is not None:
                # Non-paragraph questions break out of the current passage group.
                if q["question_type"] != "paragraph":
                    current_passage = None
                results.append(q)

    return results
