"""Transform step: read OCR output .md files and parse them into structured dicts."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import TRANSFORM_MODEL
from .extract import TopicContext
from .llm_transform_exercises import llm_extract_exercises_items


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
        out_path = outputs_dir / "contents.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved → {out_path.name}")
        return TransformResult(content_type=content_type, items=items)

    # Include answer key pages if present — passed to LLM together so it can
    # directly populate correct_answers while extracting questions.
    key_outputs_dir = ctx.outputs_dir / "exercises_outputs" / "answer_key"
    key_md_files = sorted(key_outputs_dir.glob("raw_response_*.md")) if key_outputs_dir.is_dir() else []
    all_md_files = md_files + key_md_files

    label = f"{len(md_files)} exercise page(s)"
    if key_md_files:
        label += f" + {len(key_md_files)} answer key page(s)"
    print(f"  Merging {label} and parsing via LLM ({transform_model})...")
    raw_items = llm_extract_exercises_items(all_md_files, model=transform_model)
    print(f"  → {len(raw_items)} item(s)")

    out_path = outputs_dir / "exercises.json"
    out_path.write_text(
        json.dumps({"version": 2, "items": raw_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Saved → {out_path.name}")

    flat: list[dict] = []
    for item in raw_items:
        if item["type"] == "question":
            flat.append(_normalize_question(item, passage=None, paragraph_title=None))
        elif item["type"] == "paragraph":
            for q in item.get("questions", []):
                flat.append(_normalize_question(q, passage=item.get("content"), paragraph_title=item.get("title")))
    return TransformResult(content_type=content_type, items=flat)


def _normalize_question(q: dict, passage: str | None, paragraph_title: str | None) -> dict:
    options = [o["text"] for o in q.get("options", [])]
    id_to_text = {o["id"]: o["text"] for o in q.get("options", [])}
    correct_answers = [id_to_text.get(a, a) for a in q.get("correct_answers", [])]
    return {
        "source_question_number": q.get("source_question_number"),
        "question_type": q["question_type"],
        "question_text": q["question_text"],
        "options": options,
        "correct_answers": correct_answers,
        "passage": passage,
        "paragraph_title": paragraph_title,
        "points": q.get("points", 1),
    }


def _apply_answers(raw_items: list[dict], answers: dict[str, str]) -> None:
    """Populate correct_answers on raw_items in-place using a question_number → answer mapping.

    Handles both standalone questions and nested paragraph items.
    For choice questions: if the answer is a letter (A/B/C/D), resolves to option text.
    For fill_in_the_blank/essay: stores the answer text directly.
    """
    _LETTER_TO_INDEX = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4}

    def _resolve(q: dict) -> None:
        num = q.get("source_question_number")
        if not num or str(num) not in answers:
            return
        raw_answer = answers[str(num)]
        q_type = q.get("question_type", "essay")
        options = q.get("options", [])

        if q_type in ("single_choice", "multiple_choice", "true_false") and options:
            letter = raw_answer.strip().lower()
            idx = _LETTER_TO_INDEX.get(letter)
            if idx is not None and idx < len(options):
                resolved = options[idx]["text"] if isinstance(options[0], dict) else options[idx]
                q["correct_answers"] = [resolved]
            else:
                q["correct_answers"] = [raw_answer]
        else:
            q["correct_answers"] = [raw_answer]

    for item in raw_items:
        if item.get("type") == "paragraph":
            for sub_q in item.get("questions", []):
                _resolve(sub_q)
        else:
            _resolve(item)


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

