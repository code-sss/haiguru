"""Populate course path node hierarchy and topics from the content root folder structure.

Walks <content-root>/<category>/<grade>/<subject>/<volume>/<topic> and upserts
all rows into categories, course_path_nodes, and topics.
No topic_contents are created.

Usage:
    uv run python populate_hierarchy.py --content-root C:/github/siva/SVC
"""

import argparse
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import DATABASE_URL
from db.ops import get_or_create_category, get_or_create_node, get_or_create_topic

# Subfolders that indicate a directory is a topic folder, not a hierarchy node.
_TOPIC_SUBFOLDERS = {"inputs", "outputs", "prompts"}


def _is_topic_dir(path: Path) -> bool:
    children = {p.name for p in path.iterdir() if p.is_dir()}
    return bool(children & _TOPIC_SUBFOLDERS)


def populate(content_root: str) -> None:
    root = Path(content_root).resolve()
    if not root.is_dir():
        raise ValueError(f"content-root does not exist: {root}")

    engine = create_engine(DATABASE_URL)

    # The root folder itself (e.g. "SVC") is the category.
    category_name = root.name

    with Session(engine) as session:
        category = get_or_create_category(session, category_name)

        for grade_dir in sorted(root.iterdir()):
            if not grade_dir.is_dir():
                continue

            grade_node = get_or_create_node(
                session, grade_dir.name, "grade", category.id
            )

            for subject_dir in sorted(grade_dir.iterdir()):
                if not subject_dir.is_dir():
                    continue

                subject_node = get_or_create_node(
                    session, subject_dir.name, "subject", category.id, parent_id=grade_node.id
                )

                for volume_dir in sorted(subject_dir.iterdir()):
                    if not volume_dir.is_dir():
                        continue

                    course_node = get_or_create_node(
                        session, volume_dir.name, "course", category.id, parent_id=subject_node.id
                    )

                    for topic_dir in sorted(volume_dir.iterdir()):
                        if not topic_dir.is_dir() or not _is_topic_dir(topic_dir):
                            continue

                        get_or_create_topic(session, topic_dir.name, course_node.id)

        session.commit()
        print("\nDone.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="populate_hierarchy")
    parser.add_argument(
        "--content-root",
        required=True,
        help="Path to the content root folder (e.g. C:/github/siva/SVC)",
    )
    args = parser.parse_args(argv)
    print(f"\n=== Populate Hierarchy ===")
    print(f"Root: {args.content_root}\n")
    populate(args.content_root)


if __name__ == "__main__":
    main()
