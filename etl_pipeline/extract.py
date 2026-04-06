"""Extract step: validate a topic folder, parse its metadata, and run OCR."""

from dataclasses import dataclass
from pathlib import Path

from glm_ocr.runner import run_on_folder
from glm_ocr.utils import list_image_files


@dataclass
class TopicContext:
    """All metadata and paths derived from a topic folder."""
    category_name: str   # content root folder name, e.g. "SVC"
    grade: str           # e.g. "GRADE_7"
    subject: str         # e.g. "MATHEMATICS"
    volume: str          # e.g. "VOLUME_1"
    topic: str           # e.g. "INTEGERS"
    topic_path: Path
    outputs_dir: Path


def extract(topic_path: str) -> TopicContext:
    """Validate a topic folder and return a TopicContext.

    The folder must be exactly 5 levels deep:
        <category>/<grade>/<subject>/<volume>/<topic>

    The last 5 parts of the path are used — no separate root argument needed.

    Raises ValueError if the path is too shallow or does not exist.
    """
    topic = Path(topic_path).resolve()

    if not topic.is_dir():
        raise ValueError(f"topic_path does not exist or is not a directory: {topic}")

    parts = topic.parts
    if len(parts) < 5:
        raise ValueError(
            f"Path too shallow — expected at least <category>/<grade>/<subject>/<volume>/<topic>, got: {topic}"
        )

    category_name, grade, subject, volume, topic_name = parts[-5], parts[-4], parts[-3], parts[-2], parts[-1]

    return TopicContext(
        category_name=category_name,
        grade=grade,
        subject=subject,
        volume=volume,
        topic=topic_name,
        topic_path=topic,
        outputs_dir=topic / "outputs",
    )


def run_ocr(
    ctx: TopicContext,
    content_type: str = "contents",
    model: str = "glm-ocr-optimized",
    overwrite: bool = False,
) -> None:
    """Run glm_ocr on images in ctx.topic_path/inputs/{content_type}/.

    Outputs are saved to ctx.outputs_dir/{content_type}_outputs/.
    Skips gracefully if the inputs directory does not exist.
    Skips images that already have output unless overwrite=True.
    """
    inputs_dir = ctx.topic_path / "inputs" / content_type
    if not inputs_dir.is_dir():
        print(f"[Extract] inputs/{content_type}/ not found, skipping OCR.")
        return

    images = list(list_image_files(str(ctx.topic_path), content_type))
    if not images:
        print(f"[Extract] No images found in inputs/{content_type}/, skipping OCR.")
        return

    print(f"\n[Extract] {ctx.topic} ({content_type}) — {len(images)} image(s)")
    run_on_folder(str(ctx.topic_path), model=model, content_type=content_type, overwrite=overwrite)
