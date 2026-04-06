import os
import re
from typing import Optional


def read_prompt_file(folder_path: str) -> Optional[str]:
    """Look for prompt.md or prompt.txt inside folder_path and return contents if found."""
    for name in ("prompt.md", "prompt.txt"):
        path = os.path.join(folder_path, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return None


def list_image_files(folder_path: str):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
    for entry in sorted(os.listdir(folder_path)):
        p = os.path.join(folder_path, entry)
        if os.path.isfile(p) and os.path.splitext(entry.lower())[1] in exts:
            yield p


def check_quality(response: str) -> list:
    """Run heuristic quality checks on an extracted theory response.

    Returns a list of warning strings. An empty list means no issues detected.
    """
    warnings = []

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



