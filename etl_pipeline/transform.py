"""Transform step: read OCR output .md files and parse them into structured dicts."""

from dataclasses import dataclass, field
from pathlib import Path

from .extract import TopicContext
from .parse_exercises import parse_exercises_file


@dataclass
class TransformResult:
    """Parsed content ready for the load step."""
    content_type: str          # "contents" | "exercises"
    items: list[dict] = field(default_factory=list)


def transform(ctx: TopicContext, content_type: str = "contents") -> TransformResult:
    """Read raw_response_*.md files from outputs and parse them into structured dicts.

    For contents: returns dicts with keys: title, text, order.
    For exercises: returns a flat list of question dicts (see parse_exercises_file).

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

    # exercises
    items = []
    for md_path in md_files:
        questions = parse_exercises_file(md_path)
        items.extend(questions)
    return TransformResult(content_type=content_type, items=items)

