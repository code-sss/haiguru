"""LLM-based transform for exercises: parse raw OCR markdown into structured question dicts.

Instead of relying on fixed markers in the OCR output, this module sends the raw text to a
local Ollama text model and asks it to return a JSON array of question objects.
"""

import json
import re
import warnings
from pathlib import Path

from glm_ocr.client import send_text_request_streaming
from llm_factory import make_llm

_PROMPT_TEMPLATE = """\
/no_think
You are an expert at parsing raw OCR text from school textbook exercise pages.

Given the raw text below, extract ALL questions and return them as a JSON array.
Each element must follow this exact structure:

{{
  "question_type": "<type>",
  "question_text": "<full question text, including sub-parts if any>",
  "options": ["<option A text>", "<option B text>", ...],
  "correct_answers": ["<answer text>"],
  "passage": "<passage text>" or null
}}

Rules for question_type (pick exactly one):
- "essay"            — open-ended; no options (VSAQ / SAQ / LAQ sections)
- "fill_in_the_blank"— sentence with a blank to fill
- "single_choice"    — exactly one correct answer from (A)/(B)/(C)/(D) options
- "multiple_choice"  — more than one correct answer from options
- "true_false"       — True / False question

Rules for options:
- List the option texts WITHOUT the letter prefix, e.g. ["18", "24", "30"].
- Empty list [] when there are no options.

Rules for correct_answers:
- If the answer is given in the text, include it (as the option text, not the letter).
- If not shown, use an empty list [].

Rules for passage:
- For Linked Comprehension (LCT) or paragraph questions that follow a shared passage,
  set "passage" to the passage text for every sub-question in that group.
- For standalone questions set "passage" to null.

Do NOT include:
- Section headings (VSAQ, SAQ, EXERCISE-1, etc.)
- Page numbers or figure references
- Question numbers (01., 02. …) — strip them from question_text

Return ONLY a valid JSON array. No explanation, no markdown fences.

Raw exercise text:
{raw_text}

JSON array:"""


def llm_parse_exercises(md_path: Path, model: str) -> list[dict]:
    """Use an LLM (Ollama, OpenAI, Anthropic, or TogetherAI) to parse a raw exercises
    markdown file. The model spec follows the same provider prefix convention as the
    rest of the codebase (e.g. "openai://gpt-4o-mini", "anthropic://...", or a plain
    Ollama model name).

    Returns a list of question dicts with keys:
        question_type, question_text, options, correct_answers, passage
    Returns an empty list (with a warning) on failure.
    """
    raw_text = md_path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []

    prompt = _PROMPT_TEMPLATE.format(raw_text=raw_text)

    try:
        if "://" not in model:
            # Ollama — stream for interruptibility
            response = "".join(send_text_request_streaming(model, prompt))
        else:
            # Cloud provider via llm_factory — stream for interruptibility
            llm = make_llm(model)
            response = "".join(chunk.delta for chunk in llm.stream_complete(prompt))
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        warnings.warn(
            f"[llm_transform] Ollama call failed for {md_path.name}: {exc}",
            stacklevel=2,
        )
        return []

    # Strip <think>...</think> blocks (qwen3 and similar reasoning models)
    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)

    # Strip markdown code fences that some models add
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Extract the outermost JSON array — find the first '[' and its matching ']'
    start = cleaned.find("[")
    if start == -1:
        warnings.warn(
            f"[llm_transform] No JSON array found in LLM response for {md_path.name}.\n"
            f"  Raw response (first 500 chars): {response[:500]}",
            stacklevel=2,
        )
        return []

    # Walk forward to find the balanced closing bracket
    depth = 0
    end = -1
    for i, ch in enumerate(cleaned[start:], start=start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        warnings.warn(
            f"[llm_transform] Unbalanced JSON array in LLM response for {md_path.name}.\n"
            f"  Raw response (first 500 chars): {response[:500]}",
            stacklevel=2,
        )
        return []

    try:
        questions = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        warnings.warn(
            f"[llm_transform] JSON parse error for {md_path.name}: {exc}\n"
            f"  Raw response (first 500 chars): {response[:500]}",
            stacklevel=2,
        )
        return []

    # Normalise each entry to guarantee expected keys
    normalised = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        normalised.append({
            "question_type": q.get("question_type", "essay"),
            "question_text": q.get("question_text", ""),
            "options": q.get("options") or [],
            "correct_answers": q.get("correct_answers") or [],
            "passage": q.get("passage"),
        })

    return normalised
