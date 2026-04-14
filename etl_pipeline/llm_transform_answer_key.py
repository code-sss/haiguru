"""LLM-based transform for answer key images: parse raw OCR text into a number→answer mapping."""

import json
import re
import warnings
from pathlib import Path

from glm_ocr.client import send_text_request_streaming
from llm_factory import make_llm

_PROMPT_TEMPLATE = """\
/no_think
You are extracting answers from a school exam answer key page.

Given the raw OCR text below, identify every question number and its answer.
Return a JSON object with a single key "answers" mapping question number strings to answer strings.

Examples of valid output:
{{"answers": {{"1": "A", "2": "5", "3": "True", "4": "-810", "5": "B"}}}}

Rules:
- Keys are the question numbers exactly as written (e.g. "1", "2", "3(a)").
- Values are the answer text exactly as written (e.g. "A", "B", "C", "D", "True", "False", or a numeric/text answer).
- If the answer is a letter like (A), A), A. or just A — normalise it to the uppercase letter only (e.g. "A").
- Include every answer you can find; skip nothing.
- Return ONLY valid JSON. No explanation, no markdown fences.

Raw answer key text:
{raw_text}

JSON:"""


def llm_extract_answer_key(md_paths: list[Path], model: str) -> dict[str, str]:
    """Parse one or more answer key OCR markdown files into a question_number → answer dict.

    Multiple pages are concatenated and sent as a single LLM request so the model can
    resolve any continuation across pages.

    Returns an empty dict (with a warning) on failure.
    """
    combined = "\n\n".join(
        p.read_text(encoding="utf-8").strip() for p in md_paths if p.exists()
    )
    if not combined:
        return {}

    prompt = _PROMPT_TEMPLATE.format(raw_text=combined)

    try:
        if "://" not in model:
            response = "".join(send_text_request_streaming(model, prompt))
        else:
            llm = make_llm(model)
            response = "".join(chunk.delta for chunk in llm.stream_complete(prompt))
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        warnings.warn(f"[llm_answer_key] LLM call failed: {exc}", stacklevel=2)
        return {}

    # Strip <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Find the outermost JSON object
    start = cleaned.find("{")
    if start == -1:
        warnings.warn(
            f"[llm_answer_key] No JSON object found in response.\n"
            f"  Raw (first 500): {response[:500]}",
            stacklevel=2,
        )
        return {}

    depth = 0
    end = -1
    for i, ch in enumerate(cleaned[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        warnings.warn(
            f"[llm_answer_key] Unbalanced JSON in response.\n"
            f"  Raw (first 500): {response[:500]}",
            stacklevel=2,
        )
        return {}

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        warnings.warn(f"[llm_answer_key] JSON parse error: {exc}", stacklevel=2)
        return {}

    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        warnings.warn("[llm_answer_key] 'answers' key is not a dict.", stacklevel=2)
        return {}

    return {str(k): str(v) for k, v in answers.items()}
