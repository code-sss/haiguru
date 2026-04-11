"""CLI entry-point for eval_pipeline — grade a completed exam session.

Usage:
    uv run python -m eval_pipeline --session-id <uuid>
    uv run python -m eval_pipeline --session-id <uuid> --ocr-model glm4v:9b
    uv run python -m eval_pipeline --session-id <uuid> --eval-model openai://gpt-4o
"""

from __future__ import annotations

import argparse
import sys
import warnings

from config import EVAL_MODEL, LLM_CONTEXT_WINDOW, LLM_REQUEST_TIMEOUT
from eval_pipeline.judge import JudgeResult, grade_subjective, resolve_model_answer
from eval_pipeline.load import (
    QuestionResult,
    SessionItem,
    load_session,
    save_results,
)
from eval_pipeline.ocr import run_ocr_for_answer
from llm_factory import make_llm
from eval_pipeline.grading import grade_question

_OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false", "fill_in_the_blank"}
_SUBJECTIVE_TYPES = {"essay"}
_DEFAULT_OCR_MODEL = "glm-ocr-optimized"


# ---------------------------------------------------------------------------
# Core per-question grader
# ---------------------------------------------------------------------------


def _grade_one(item: SessionItem, llm, ocr_model: str) -> QuestionResult:
    """Grade a single SessionItem and return a QuestionResult.

    Dispatch table (matches PLAN.md):
      image: + objective  → OCR → grade_question
      image: + essay      → OCR → grade_subjective
      text   + objective  → grade_question
      text   + essay      → grade_subjective
      null/empty          → warn, 0 pts
    """
    esq = item.esq
    question = item.question
    points = esq.points or 0
    qt = question.question_type
    ocr_text: str | None = None  # set only when we replace the image: prefix

    # --- Resolve user answer ---
    if item.image_path is not None:
        # Handwritten answer — run OCR first
        try:
            ocr_text = run_ocr_for_answer(item.image_path, ocr_model)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Image file missing for ESQ {esq.id}: {exc}"
            ) from exc
        user_answer = ocr_text
    else:
        user_answer = esq.user_answer

    # --- Empty / unanswered ---
    if not user_answer or not user_answer.strip():
        warnings.warn(f"[eval] ESQ {esq.id}: empty answer — grading as unanswered (0 pts)")
        return QuestionResult(
            esq_id=esq.id,
            earned_points=0.0,
            is_correct=False,
            user_answer=ocr_text,
        )

    # --- Objective grading ---
    if qt in _OBJECTIVE_TYPES:
        is_correct, earned = grade_question(user_answer, points, question)
        return QuestionResult(
            esq_id=esq.id,
            earned_points=earned,
            is_correct=is_correct,
            user_answer=ocr_text,
        )

    # --- Subjective (essay) grading ---
    if qt in _SUBJECTIVE_TYPES:
        model_answer = resolve_model_answer(question)
        result: JudgeResult = grade_subjective(
            question_text=question.question_text,
            model_answer=model_answer,
            student_answer=user_answer,
            points=points,
            llm=llm,
        )
        return QuestionResult(
            esq_id=esq.id,
            earned_points=result.awarded,
            is_correct=None,  # essay — no binary correct/incorrect
            user_answer=ocr_text,
        )

    # --- Unknown type — warn and skip ---
    warnings.warn(
        f"[eval] ESQ {esq.id}: unknown question_type {qt!r} — grading as unanswered (0 pts)"
    )
    return QuestionResult(
        esq_id=esq.id,
        earned_points=0.0,
        is_correct=None,
        user_answer=ocr_text,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grade a completed exam session (eval_pipeline)"
    )
    parser.add_argument("--session-id", required=True, help="UUID of the ExamSession to grade")
    parser.add_argument(
        "--ocr-model",
        default=_DEFAULT_OCR_MODEL,
        help=f"Ollama vision model for handwritten OCR (default: {_DEFAULT_OCR_MODEL})",
    )
    parser.add_argument(
        "--eval-model",
        default=EVAL_MODEL,
        help=f"LLM for essay grading (default: {EVAL_MODEL}). "
             "Supports openai://, anthropic://, together://, or plain Ollama name.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Load session
    try:
        session = load_session(args.session_id)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not session.items:
        print(f"No ungraded questions found for session {args.session_id}. Nothing to do.")
        sys.exit(0)

    print(f"Session  : {session.session_id}")
    print(f"User     : {session.user_id}")
    print(f"Items    : {len(session.items)} ungraded question(s)")
    print(f"OCR model: {args.ocr_model}")
    print(f"Eval model: {args.eval_model}")
    print("-" * 60)

    # Build LLM once (only needed if any essay questions are present)
    has_essay = any(item.question.question_type in _SUBJECTIVE_TYPES for item in session.items)
    llm = (
        make_llm(args.eval_model, request_timeout=LLM_REQUEST_TIMEOUT, context_window=LLM_CONTEXT_WINDOW)
        if has_essay
        else None
    )

    # Grade each item
    results: list[QuestionResult] = []
    for item in session.items:
        try:
            result = _grade_one(item, llm, args.ocr_model)
            results.append(result)
            print(
                f"  ESQ {item.esq.id} | type={item.question.question_type}"
                f" | earned={result.earned_points}/{item.esq.points or 0}"
            )
        except RuntimeError as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    # Persist
    save_results(args.session_id, results)
    print("-" * 60)
    print(f"Saved {len(results)} result(s). Session score updated.")


if __name__ == "__main__":
    main()
