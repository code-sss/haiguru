"""Extract step: validate a topic folder and parse its metadata from the path."""

from dataclasses import dataclass, field
from pathlib import Path

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
    image_paths: list[str] = field(default_factory=list)


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

    image_paths = list(list_image_files(str(topic)))

    return TopicContext(
        category_name=category_name,
        grade=grade,
        subject=subject,
        volume=volume,
        topic=topic_name,
        topic_path=topic,
        outputs_dir=topic / "outputs",
        image_paths=image_paths,
    )
