"""ETL pipeline entry point.

Usage:
    uv run python -m etl_pipeline --topic-path <path>

Flags:
    --skip-transform    Skip OCR step (use existing .md files)
    --skip-load         Skip DB load step
    --overwrite         Re-run OCR even if output files already exist
    --model             Ollama model name (default: glm-ocr-optimized)
"""

import argparse

from .extract import extract
from .transform import transform
from .load import load


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m etl_pipeline")
    parser.add_argument("--topic-path", required=True, help="Path to the topic folder (e.g. .../SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS)")
    parser.add_argument("--model", default="glm-ocr-optimized", help="Ollama OCR model name")
    parser.add_argument("--overwrite", action="store_true", help="Re-run OCR even for already-processed images")
    parser.add_argument("--skip-transform", action="store_true", help="Skip OCR step")
    parser.add_argument("--skip-load", action="store_true", help="Skip DB load step")
    args = parser.parse_args(argv)

    print(f"\n=== ETL Pipeline ===")

    # Extract
    ctx = extract(args.topic_path)
    print(f"[Extract] {ctx.category_name} / {ctx.grade} / {ctx.subject} / {ctx.volume} / {ctx.topic}")
    print(f"          {len(ctx.image_paths)} image(s) found")

    # Transform
    if not args.skip_transform:
        transform(ctx, model=args.model, overwrite=args.overwrite)
    else:
        print("\n[Transform] Skipped.")

    # Load
    if not args.skip_load:
        load(ctx)
    else:
        print("\n[Load] Skipped.")


if __name__ == "__main__":
    main()
