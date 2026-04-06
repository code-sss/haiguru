import os
import re
from typing import Optional


def read_prompt_file(folder_path: str, content_type: str = "contents") -> Optional[str]:
    """Look for {content_type}_prompt.md inside folder_path/prompts/ and return contents if found."""
    path = os.path.join(folder_path, "prompts", f"{content_type}_prompt.md")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def list_image_files(folder_path: str, content_type: str = "contents"):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    inputs_dir = os.path.join(folder_path, "inputs", content_type)
    for entry in sorted(os.listdir(inputs_dir)):
        p = os.path.join(inputs_dir, entry)
        if os.path.isfile(p) and os.path.splitext(entry.lower())[1] in exts:
            yield p


def check_quality(response: str, content_type: str = "contents") -> list:
    """Run heuristic quality checks on an OCR response.

    Returns a list of warning strings. An empty list means no issues detected.
    """
    warnings = []

    if content_type == "exercises":
        if "### QUESTION" not in response:
            warnings.append("No '### QUESTION' markers found — extraction may have failed or model ignored the output format.")
        if len(response.strip()) < 100:
            warnings.append(f"Response is very short ({len(response.strip())} chars) — extraction may have failed.")
        return warnings

    # contents branch
    if "### CONTENT" not in response:
        warnings.append("Missing '### CONTENT' section header — model may have ignored the output format.")

    content = response.split("### CONTENT", 1)[-1].strip()
    if len(content) < 100:
        warnings.append(f"Content is very short ({len(content)} chars) — extraction may have failed.")

    question_patterns = [
        (r"^\s*Q\.\s*\d+", "Lines starting with 'Q.<number>' detected — may contain questions."),
        (r"^\s*\d+\.\s+.+\?", "Numbered lines ending with '?' detected — may contain questions."),
        (r"^\s*\([a-d]\)\s+", "Option patterns like '(a)' detected — may contain MCQ options."),
    ]
    for pattern, message in question_patterns:
        if re.search(pattern, response, re.MULTILINE | re.IGNORECASE):
            warnings.append(message)

    return warnings



