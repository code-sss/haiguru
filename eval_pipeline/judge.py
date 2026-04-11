"""LLM judge for subjective (essay) grading in eval_pipeline."""

from __future__ import annotations

import json
import re
import uuid
import warnings
from dataclasses import dataclass

from llama_index.core.llms import LLM

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```[^\n]*\n?|```$", re.MULTILINE)

_JUDGE_PROMPT = """\
You are a strict exam evaluator. Grade the student's answer.

Question: {question_text}
Model answer: {model_answer}
Student answer: {student_answer}
Max marks: {points}

Return only valid JSON:
{{"awarded": <float>, "max_marks": <int>, "remark": "<brief feedback>"}}"""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class JudgeResult:
    awarded: float
    max_marks: int
    remark: str


# ---------------------------------------------------------------------------
# JSON parsing (tested independently — most bugs live here)
# ---------------------------------------------------------------------------


def _parse_json_response(text: str, points: int) -> JudgeResult:
    """Extract a JudgeResult from raw LLM output.

    Strategy:
      1. Strip <think>…</think> blocks (qwen3 models).
      2. Strip markdown code fences.
      3. Try json.loads on the cleaned string.
      4. Fallback: extract the first {...} block with regex and parse that.
      5. On any parse failure: return a zero-score result and warn.
    """
    # Step 1 — strip thinking blocks
    cleaned = _THINK_RE.sub("", text).strip()
    # Step 2 — strip markdown fences
    cleaned = _FENCE_RE.sub("", cleaned).strip()

    def _from_dict(d: dict) -> JudgeResult:
        awarded = float(d.get("awarded", 0.0))
        awarded = max(0.0, min(awarded, float(points)))  # clamp
        return JudgeResult(
            awarded=awarded,
            max_marks=int(d.get("max_marks", points)),
            remark=str(d.get("remark", "")),
        )

    # Step 3 — direct parse
    try:
        return _from_dict(json.loads(cleaned))
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Step 4 — regex fallback: grab first {...} block
    match = re.search(r"\{[\s\S]*?\}", cleaned)
    if match:
        try:
            return _from_dict(json.loads(match.group()))
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    # Step 5 — give up
    warnings.warn(
        f"[judge] Failed to parse LLM response as JSON. "
        f"Raw text (first 200 chars): {text[:200]!r}"
    )
    return JudgeResult(awarded=0.0, max_marks=points, remark="parse error")


# ---------------------------------------------------------------------------
# RAG fallback for empty correct_answers
# ---------------------------------------------------------------------------


def _rag_retrieve_model_answer(topic_id: uuid.UUID, question_text: str) -> str:
    """Retrieve relevant topic content chunks as a model-answer stand-in.

    Used only when ``question.correct_answers`` is empty (Decision #2).
    Imports are deferred so the embed model is not loaded on every invocation.
    """
    from llama_index.core.vector_stores.types import (
        FilterOperator,
        MetadataFilter,
        MetadataFilters,
    )

    from rag.retriever import build_retriever

    filters = MetadataFilters(
        filters=[
            MetadataFilter(
                key="topic_id",
                value=str(topic_id),
                operator=FilterOperator.EQ,
            )
        ]
    )
    retriever = build_retriever(top_k=3, filters=filters)
    nodes = retriever.retrieve(question_text)
    return "\n\n".join(n.text for n in nodes if n.text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def grade_subjective(
    question_text: str,
    model_answer: str,
    student_answer: str,
    points: int,
    llm: LLM,
) -> JudgeResult:
    """Grade an essay question using an LLM judge.

    Args:
        question_text:  The question as written in the exam.
        model_answer:   Expected answer (from ``correct_answers`` or RAG fallback).
        student_answer: The student's transcribed or typed answer.
        points:         Max marks for this question.
        llm:            A LlamaIndex LLM instance (from ``llm_factory.make_llm``).

    Returns:
        :class:`JudgeResult` with ``awarded`` clamped to ``[0.0, points]``.
    """
    prompt = _JUDGE_PROMPT.format(
        question_text=question_text,
        model_answer=model_answer,
        student_answer=student_answer,
        points=points,
    )
    raw = llm.complete(prompt).text
    return _parse_json_response(raw, points)


def resolve_model_answer(question) -> str:
    """Return the model answer string for *question*.

    Uses ``correct_answers`` when populated; falls back to RAG retrieval and
    warns when it is empty (Decision #2).
    """
    model_answer = "; ".join(question.correct_answers or [])
    if not model_answer:
        warnings.warn(
            f"[judge] question {question.id}: correct_answers empty, "
            "using RAG fallback"
        )
        model_answer = _rag_retrieve_model_answer(question.topic_id, question.question_text)
    return model_answer
