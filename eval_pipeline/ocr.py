"""OCR step for eval_pipeline.

Converts a handwritten-answer image to text using an Ollama vision model.
"""

from __future__ import annotations

import os

from glm_ocr.client import get_optimized_image_b64, send_single_request

OCR_PROMPT = (
    "Transcribe the handwritten text exactly, preserving question numbers and answers."
)


def run_ocr_for_answer(image_path: str, model: str) -> str:
    """Return transcribed text for the handwritten answer at *image_path*.

    Args:
        image_path: Absolute or relative filesystem path to the image file.
        model: Ollama vision model name (e.g. ``"glm4v:9b"``).

    Raises:
        FileNotFoundError: if *image_path* does not exist on disk.

    Returns:
        Raw transcribed text from the vision model.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"OCR image not found: {image_path}")

    b64 = get_optimized_image_b64(image_path)
    return send_single_request(model, OCR_PROMPT, [b64])
