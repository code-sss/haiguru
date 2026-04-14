"""ETL pipeline entry point.

Usage:
    # Full OCR pipeline
    uv run python -m etl_pipeline --topic-path <path> --etl-contents
    uv run python -m etl_pipeline --topic-path <path> --etl-exercises
    uv run python -m etl_pipeline --topic-path <path> --etl-contents --etl-exercises

    # Load exercises from a JSON file
    uv run python -m etl_pipeline --load-exercises <json_file> --course-node-id <uuid>
    uv run python -m etl_pipeline --load-exercises <json_file> --course-node-id <uuid> --topic-id <uuid>
    uv run python -m etl_pipeline --load-exercises <json_file> --topic-path <path>

Flags:
    --etl-contents          Run full extract→transform→load pipeline for contents
    --etl-exercises         Run full extract→transform→load pipeline for exercises (OCR + LLM)
    --load-exercises        Load exercises directly from a JSON file (bypasses extract + transform)
    --course-node-id        course_path_node UUID for the exam template (used with --load-exercises)
    --topic-id              Optional topic UUID to link questions to (used with --load-exercises + --course-node-id)
    --created-by            UUID written to exam_template.created_by (default: system UUID)
    --topic-path            Topic folder path — required for --etl-* flags; also accepted by --load-exercises
                            to derive course node and create/look up the topic automatically
    --skip-extract          Skip OCR step (use existing .md files); applies to --etl-* flags
    --skip-transform        Skip LLM transform step; use with --skip-load to run OCR only
    --skip-load             Skip DB load step
    --overwrite             Re-run OCR even if output files already exist
    --model                 Ollama OCR model name (default: glm-ocr-optimized)
    --transform-model       Override LLM used to parse exercises (default: TRANSFORM_MODEL from .env)
"""

import argparse
import uuid

from config import TRANSFORM_MODEL
from .extract import extract, run_ocr
from .transform import transform, transform_json_exercises
from .load import load, load_json_exercises


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m etl_pipeline")
    parser.add_argument("--topic-path", default=None, help="Path to the topic folder (e.g. .../GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS under the content root)")
    parser.add_argument("--etl-contents", action="store_true", help="Run full extract→transform→load pipeline for contents")
    parser.add_argument("--etl-exercises", action="store_true", help="Run full extract→transform→load pipeline for exercises (OCR + LLM transform)")
    parser.add_argument("--load-exercises", default=None, metavar="JSON_FILE", help="Load exercises directly from a JSON file, bypassing extract and transform")
    parser.add_argument("--course-node-id", default=None, help="course_path_node UUID for the exam template (used with --load-exercises)")
    parser.add_argument("--topic-id", default=None, help="Topic UUID to link questions to (optional, used with --load-exercises + --course-node-id)")
    parser.add_argument("--created-by", default=None, help="UUID written to exam_template.created_by (default: system UUID)")
    parser.add_argument("--model", default="glm-ocr-optimized", help="Ollama OCR model name")
    parser.add_argument("--transform-model", default=None, help="Ollama text model for LLM-based exercise transform (default: TRANSFORM_MODEL from .env)")
    parser.add_argument("--overwrite", action="store_true", help="Re-run OCR even for already-processed images")
    parser.add_argument("--skip-extract", action="store_true", help="Skip OCR step (use existing .md files)")
    parser.add_argument("--skip-transform", action="store_true", help="Skip LLM transform step (use --skip-transform --skip-load to run OCR only)")
    parser.add_argument("--skip-load", action="store_true", help="Skip DB load step")
    args = parser.parse_args(argv)

    print(f"\n=== ETL Pipeline ===")

    # -------------------------------------------------------------------------
    # --load-exercises path: JSON → questions + paragraph_questions + exam template
    # -------------------------------------------------------------------------
    if args.load_exercises:
        if args.topic_path and args.course_node_id:
            parser.error("--topic-path and --course-node-id are mutually exclusive with --load-exercises")

        if not args.topic_path and not args.course_node_id:
            parser.error("--load-exercises requires either --topic-path or --course-node-id")

        created_by = uuid.UUID(args.created_by) if args.created_by else None
        result = transform_json_exercises(args.load_exercises)

        if not args.skip_load:
            if args.topic_path:
                ctx = extract(args.topic_path)
                print(f"[Extract] {ctx.category_name} / {ctx.grade} / {ctx.subject} / {ctx.volume} / {ctx.topic}")
                load_json_exercises(result, created_by=created_by, ctx=ctx)
            else:
                course_node_id = uuid.UUID(args.course_node_id)
                topic_id = uuid.UUID(args.topic_id) if args.topic_id else None
                load_json_exercises(result, created_by=created_by, course_node_id=course_node_id, topic_id=topic_id)
        else:
            print("\n[Load] Skipped.")
        return

    # -------------------------------------------------------------------------
    # --etl-contents / --etl-exercises path: full OCR → transform → load
    # -------------------------------------------------------------------------
    if not args.etl_contents and not args.etl_exercises:
        parser.error("Specify at least one of: --etl-contents, --etl-exercises, --load-exercises")

    if not args.topic_path:
        parser.error("--topic-path is required for --etl-contents and --etl-exercises")

    ctx = extract(args.topic_path)
    print(f"[Extract] {ctx.category_name} / {ctx.grade} / {ctx.subject} / {ctx.volume} / {ctx.topic}")

    types_to_run = []
    if args.etl_contents:
        types_to_run.append("contents")
    if args.etl_exercises:
        types_to_run.append("exercises")

    # Extract — OCR
    if not args.skip_extract:
        for t in types_to_run:
            run_ocr(ctx, content_type=t, model=args.model, overwrite=args.overwrite)
        # When exercises are being processed, also OCR answer key if images are present.
        # Images: inputs/exercises/answer_key/  Prompt: prompts/answer_key_prompt.md
        # Outputs: outputs/exercises_outputs/answer_key/
        if args.etl_exercises:
            run_ocr(ctx, content_type="answer_key", model=args.model, overwrite=args.overwrite,
                    images_subpath="exercises/answer_key",
                    output_subpath="exercises_outputs/answer_key")
    else:
        print("[Extract] OCR skipped.")

    # Transform — read .md files and parse into structured dicts
    transform_model = args.transform_model or TRANSFORM_MODEL
    if not args.skip_transform:
        results = [transform(ctx, content_type=t, transform_model=transform_model) for t in types_to_run]
    else:
        print("[Transform] Skipped.")
        results = []
        for t in types_to_run:
            json_path = ctx.outputs_dir / f"{t}_outputs" / f"{t}.json"
            if json_path.exists():
                print(f"[Transform] Loading existing {json_path.name} for {t}.")
                results.append(transform_json_exercises(str(json_path)) if t == "exercises" else transform(ctx, content_type=t, transform_model=transform_model))
            else:
                print(f"[Transform] No existing {json_path.name} found for {t} — skipping load.")

    # Load — write to Postgres
    if not args.skip_load:
        for result in results:
            load(ctx, result)
    else:
        print("\n[Load] Skipped.")


if __name__ == "__main__":
    main()
