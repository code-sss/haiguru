"""ETL pipeline entry point.

Usage:
    uv run python -m etl_pipeline --topic-path <path>

Flags:
    --type              contents | exercises | both (default: contents)
    --skip-extract      Skip OCR step (use existing .md files)
    --skip-load         Skip DB load step
    --overwrite         Re-run OCR even if output files already exist
    --model             Ollama model name (default: glm-ocr-optimized)
"""

import argparse

from .extract import extract, run_ocr
from .transform import transform
from .load import load


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m etl_pipeline")
    parser.add_argument("--topic-path", required=True, help="Path to the topic folder (e.g. .../GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS under the content root)")
    parser.add_argument("--type", choices=["contents", "exercises", "both"], default="contents", help="What to process: contents, exercises, or both")
    parser.add_argument("--model", default="glm-ocr-optimized", help="Ollama OCR model name")
    parser.add_argument("--overwrite", action="store_true", help="Re-run OCR even for already-processed images")
    parser.add_argument("--skip-extract", action="store_true", help="Skip OCR step (use existing .md files)")
    parser.add_argument("--skip-load", action="store_true", help="Skip DB load step")
    args = parser.parse_args(argv)

    print(f"\n=== ETL Pipeline ===")

    # Extract — validate + parse metadata
    ctx = extract(args.topic_path)
    print(f"[Extract] {ctx.category_name} / {ctx.grade} / {ctx.subject} / {ctx.volume} / {ctx.topic}")

    types_to_run = ["contents", "exercises"] if args.type == "both" else [args.type]

    # Extract — OCR
    if not args.skip_extract:
        for t in types_to_run:
            run_ocr(ctx, content_type=t, model=args.model, overwrite=args.overwrite)
    else:
        print("[Extract] OCR skipped.")

    # Transform — read .md files and parse into structured dicts
    results = [transform(ctx, content_type=t) for t in types_to_run]

    # Load — write to Postgres
    if not args.skip_load:
        for result in results:
            load(ctx, result)
    else:
        print("\n[Load] Skipped.")


if __name__ == "__main__":
    main()

