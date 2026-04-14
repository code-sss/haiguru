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

The input may contain both exercise pages (with questions) and answer key pages.
Answer key pages list question numbers with their correct answers (e.g. "1. A", "2. 5").

Given the raw text below, extract ALL questions and return them as a JSON array of items.
Each item must be one of these two structures:

Standalone question:
{{
  "type": "question",
  "source_question_number": "exercise-1-VSAQ-01",
  "question_type": "<type>",
  "question_text": "<full question text>",
  "options": [{{"id": "a", "text": "<option text>"}}, {{"id": "b", "text": "<option text>"}}, ...],
  "correct_answers": ["a"],
  "explanation": "<explanation or null>",
  "difficulty": "easy|medium|hard",
  "tags": ["<tag>", ...]
}}

Paragraph/passage group (linked comprehension only):
{{
  "type": "paragraph",
  "title": "<short title for the passage>",
  "content": "<full passage text>",
  "questions": [
    {{ <same structure as standalone question above> }},
    ...
  ]
}}

Rules for source_question_number:
- Format as "exercise-<N>-<section>-<number>" using the exercise number, section abbreviation,
  and the question's number within that section, zero-padded to 2 digits.
  Examples: "exercise-1-VSAQ-01", "exercise-1-SAQ-11", "exercise-2-SOC-11", "exercise-2-LCT-31".
- Section abbreviations (use exactly these regardless of how the heading is spelled):
    VSAQ — Very Short Answer Questions
    SAQ  — Short Answer Questions
    SQ   — Subjective / Long Answer Questions
    TF   — True or False
    SOC  — Single Option Correct
    MOC  — One or More Than One Option Correct
    LCT  — Linked Comprehension Type
    MMT  — Matrix Match Type
- If there is only one exercise with no section headings, use just the question number (e.g. "1", "2").
- Do NOT include the number in question_text.
- Use null only if neither a question number nor a section heading can be determined.

Rules for question_type (pick exactly one):
- "essay"             — open-ended; no options (VSAQ / SAQ / SQ sections)
- "fill_in_the_blank" — sentence with a blank to fill
- "single_choice"     — exactly one correct answer from (A)/(B)/(C)/(D) options
- "multiple_choice"   — more than one correct answer from options
- "true_false"        — True / False question

Rules for options:
- Use letter IDs: "a", "b", "c", "d" in order.
- Text is the option content WITHOUT the letter prefix, e.g. {{"id": "a", "text": "18"}}.
- Empty list [] when there are no options (essay, fill_in_the_blank).

Rules for correct_answers:
- IMPORTANT: When an answer key page is provided, always copy answers DIRECTLY from the key.
  Match by source_question_number. Do NOT compute or verify answers yourself.
- For single_choice/multiple_choice/true_false: use option IDs (e.g. ["a", "c"]).
  Convert letter answers from the key (A→"a", B→"b", C→"c", D→"d").
  For MOC keys like "ABD", expand to ["a", "b", "d"].
- For fill_in_the_blank/essay: store the answer text directly as a string in the list.
- If the answer is not in the key, use an empty list [].

Rules for multi-part questions:
- If a question has sub-parts labeled (i), (ii), (iii)... they are parts of ONE question.
  Do NOT turn sub-part answers into options. Keep it as a single question (essay or
  fill_in_the_blank) and store the combined answer as one string
  (e.g., "(i) 0, (ii) 0, (iii) not defined, (iv) 1").
- Only use options when the question explicitly offers lettered choices (A)/(B)/(C)/(D).

Rules for instruction headers:
- If a numbered question is an instruction ("Find the product using suitable property...")
  followed immediately by numbered sub-questions, do NOT emit the instruction as a
  standalone question. Instead, prepend the instruction text into the question_text of
  each sub-question.

Rules for explanation:
- Include any answer explanation or working shown in the text.
- Use null if none is present.

Rules for difficulty:
- "easy" for recall/definition questions, "medium" for application, "hard" for multi-step reasoning.
- Default to "medium" if uncertain.

Rules for paragraph groups:
- Use "paragraph" ONLY for LCT (Linked Comprehension) where 2 or more questions explicitly
  share the same passage or reading excerpt. Set "content" to the full passage text.
- True/False questions are standalone questions — do NOT group them into a paragraph.
- SOC/MOC questions each have their own options — do NOT group them into a paragraph.
- A single word problem with one question is NOT a paragraph — embed the scenario into
  question_text and return it as a standalone question.

Do NOT include:
- Section headings (VSAQ, SAQ, EXERCISE-1, TRUE OR FALSE, SOC, etc.)
- Page numbers or figure references

Return ONLY a valid JSON array. No explanation, no markdown fences.

Raw exercise text:
{raw_text}

JSON array:"""


def llm_extract_exercises_items(md_paths: list[Path], model: str) -> list[dict]:
    """Use an LLM (Ollama, OpenAI, Anthropic, or TogetherAI) to parse raw exercises
    OCR files into qa-sample.json format items.

    All pages are merged into a single LLM call so the model has full context across
    pages (consistent numbering, no cross-page split questions).

    The model spec follows the same provider prefix convention as the rest of the
    codebase (e.g. "openai://gpt-4o-mini", "anthropic://...", or a plain Ollama model name).

    Returns a list of item dicts, each with type="question" or type="paragraph".
    Returns an empty list (with a warning) on failure.
    """
    parts = [p.read_text(encoding="utf-8").strip() for p in md_paths if p.exists()]
    raw_text = "\n\n---\n\n".join(p for p in parts if p)
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
        "source_question_number": q.get("source_question_number"),
        "question_type": q.get("question_type", "essay"),
        "question_text": q.get("question_text", ""),
        "options": q.get("options") or [],
        "correct_answers": q.get("correct_answers") or [],
        "explanation": q.get("explanation"),
        "difficulty": q.get("difficulty", "medium"),
        "tags": q.get("tags") or [],
    }
