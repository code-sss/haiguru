"""Transform step: read OCR output .md files and parse them into structured dicts."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import TRANSFORM_MODEL
from .extract import TopicContext
from .llm_transform_exercises import llm_parse_exercises


@dataclass
class TransformResult:
    """Parsed content ready for the load step."""
    content_type: str          # "contents" | "exercises"
    items: list[dict] = field(default_factory=list)
    exam_template_meta: dict | None = None  # set only when loading from a JSON file


def transform(
    ctx: TopicContext,
    content_type: str = "contents",
    transform_model: str = TRANSFORM_MODEL,
) -> TransformResult:
    """Read raw_response_*.md files from outputs and parse them into structured dicts.

    For contents: returns dicts with keys: title, text, order.
    For exercises: uses an LLM (transform_model) to parse the raw OCR text into a flat
    list of question dicts with keys: question_type, question_text, options,
    correct_answers, passage.

    Skips gracefully if the outputs directory does not exist.
    """
    outputs_dir = ctx.outputs_dir / f"{content_type}_outputs"
    md_files = sorted(outputs_dir.glob("raw_response_*.md")) if outputs_dir.is_dir() else []

    if not md_files:
        print(f"[Transform] No .md files found in {outputs_dir.name}/, skipping {content_type}.")
        return TransformResult(content_type=content_type)

    print(f"\n[Transform] {ctx.topic} ({content_type}) — {len(md_files)} file(s)")

    if content_type == "contents":
        items = []
        for order, md_path in enumerate(md_files, start=1):
            text = md_path.read_text(encoding="utf-8").strip()
            if not text:
                print(f"  Skipping empty file: {md_path.name}")
                continue
            items.append({"title": md_path.name, "text": text, "order": order})
        return TransformResult(content_type=content_type, items=items)

    # exercises — LLM-based parsing
    items = []
    for md_path in md_files:
        print(f"  Parsing {md_path.name} via LLM ({transform_model})...")
        questions = llm_parse_exercises(md_path, model=transform_model)
        print(f"    → {len(questions)} question(s)")
        items.extend(questions)
    return TransformResult(content_type=content_type, items=items)


def _normalize_question(q: dict, passage: str | None, paragraph_title: str | None) -> dict:
    options = [o["text"] for o in q.get("options", [])]
    id_to_text = {o["id"]: o["text"] for o in q.get("options", [])}
    correct_answers = [id_to_text.get(a, a) for a in q.get("correct_answers", [])]
    return {
        "question_type": q["question_type"],
        "question_text": q["question_text"],
        "options": options,
        "correct_answers": correct_answers,
        "passage": passage,
        "paragraph_title": paragraph_title,
        "points": q.get("points", 1),
    }


def transform_json_exercises(json_path: str) -> TransformResult:
    """Convert a hand-authored JSON exercises file into a TransformResult.

    Handles the qa-sample.json format: top-level items are either
    type=question (standalone) or type=paragraph (with nested questions).
    Options are normalized to plain strings and correct_answers are resolved
    from option IDs to option text.

    Top-level metadata (title, description, passing_score, duration_minutes)
    is captured in exam_template_meta. passing_score > 1 is treated as a
    percentage and converted to a decimal fraction (e.g. 80 → 0.8).
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    flat: list[dict] = []
    for item in data.get("items", []):
        if item["type"] == "question":
            flat.append(_normalize_question(item, passage=None, paragraph_title=None))
        elif item["type"] == "paragraph":
            passage = item["content"]
            title = item["title"]
            for q in item.get("questions", []):
                flat.append(_normalize_question(q, passage=passage, paragraph_title=title))

    passing_score = data.get("passing_score")
    if passing_score is not None and passing_score > 1:
        passing_score = passing_score / 100

    exam_template_meta = {
        "title": data.get("title", "Untitled Exam"),
        "description": data.get("description"),
        "passing_score": passing_score,
        "duration_minutes": data.get("duration_minutes"),
        "mode": data.get("mode", "static"),
    }

    print(f"[Transform] {json_path} — {len(flat)} question(s) from JSON")
    return TransformResult(content_type="exercises", items=flat, exam_template_meta=exam_template_meta)

