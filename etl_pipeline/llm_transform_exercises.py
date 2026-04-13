"""LLM-based transform for exercises: parse raw OCR markdown into qa-sample.json format items.

Instead of relying on fixed markers in the OCR output, this module sends the raw text to a
local Ollama text model and asks it to return a JSON array of items in qa-sample.json format.
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

Given the raw text below, extract ALL questions and return them as a JSON array of items.
Each item must be one of these two structures:

Standalone question:
{{
  "type": "question",
  "question_type": "<type>",
  "question_text": "<full question text>",
  "options": [{{"id": "a", "text": "<option text>"}}, {{"id": "b", "text": "<option text>"}}, ...],
  "correct_answers": ["a"],
  "explanation": "<explanation or null>",
  "difficulty": "easy|medium|hard",
  "tags": ["<tag>", ...]
}}

Paragraph/passage group (linked comprehension):
{{
  "type": "paragraph",
  "title": "<short title for the passage>",
  "content": "<full passage text>",
  "questions": [
    {{ <same structure as standalone question above> }},
    ...
  ]
}}

Rules for question_type (pick exactly one):
- "essay"             — open-ended; no options (VSAQ / SAQ / LAQ sections)
- "fill_in_the_blank" — sentence with a blank to fill
- "single_choice"     — exactly one correct answer from (A)/(B)/(C)/(D) options
- "multiple_choice"   — more than one correct answer from options
- "true_false"        — True / False question

Rules for options:
- Use letter IDs: "a", "b", "c", "d" in order.
- Text is the option content WITHOUT the letter prefix, e.g. {{"id": "a", "text": "18"}}.
- Empty list [] when there are no options (essay, fill_in_the_blank).

Rules for correct_answers:
- Use option IDs (e.g. ["a", "c"]), not the option text.
- If the answer is not shown, use an empty list [].

Rules for explanation:
- Include any answer explanation or working shown in the text.
- Use null if none is present.

Rules for difficulty:
- "easy" for recall/definition questions, "medium" for application, "hard" for multi-step reasoning.
- Default to "medium" if uncertain.

Rules for paragraph groups:
- Use "paragraph" ONLY when 2 or more questions share the exact same passage or reading excerpt.
- A single word problem or scenario with one question is NOT a paragraph — embed the full scenario text into question_text and return it as a standalone question.
- Set "content" to the full passage text.
- Each sub-question follows the standalone question structure.

Do NOT include:
- Section headings (VSAQ, SAQ, EXERCISE-1, etc.)
- Page numbers or figure references
- Question numbers (01., 02. …) — strip them from question_text

Return ONLY a valid JSON array. No explanation, no markdown fences.

Raw exercise text:
{raw_text}

JSON array:"""


def llm_extract_exercises_items(md_path: Path, model: str) -> list[dict]:
    """Use an LLM (Ollama, OpenAI, Anthropic, or TogetherAI) to parse a raw exercises
    markdown file into qa-sample.json format items.

    The model spec follows the same provider prefix convention as the rest of the
    codebase (e.g. "openai://gpt-4o-mini", "anthropic://...", or a plain Ollama model name).

    Returns a list of item dicts, each with type="question" or type="paragraph".
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
            f"[llm_transform] LLM call failed for {md_path.name}: {exc}",
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
        items = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        warnings.warn(
            f"[llm_transform] JSON parse error for {md_path.name}: {exc}\n"
            f"  Raw response (first 500 chars): {response[:500]}",
            stacklevel=2,
        )
        return []

    # Normalise each item to guarantee expected keys
    normalised = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "question")
        if item_type == "paragraph":
            normalised.append({
                "type": "paragraph",
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "questions": [_normalise_question_item(q) for q in item.get("questions", [])],
            })
        else:
            normalised.append(_normalise_question_item(item))

    return normalised


def _normalise_question_item(q: dict) -> dict:
    """Ensure a question item has all required keys in qa-sample.json format."""
    return {
        "type": "question",
        "question_type": q.get("question_type", "essay"),
        "question_text": q.get("question_text", ""),
        "options": q.get("options") or [],
        "correct_answers": q.get("correct_answers") or [],
        "explanation": q.get("explanation"),
        "difficulty": q.get("difficulty", "medium"),
        "tags": q.get("tags") or [],
    }
