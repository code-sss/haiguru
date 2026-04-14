import os
from pathlib import Path
from typing import Optional
from .client import get_optimized_image_b64, send_streamed_request, save_raw_response
from .utils import read_prompt_file, list_image_files, check_quality


def run_on_folder(folder_path: str, model: str, content_type: str = "contents", overwrite: bool = False, images_subpath: Optional[str] = None, output_subpath: Optional[str] = None) -> None:
    """Process all images in `folder_path/inputs/{content_type}/`, using
    `folder_path/prompts/{content_type}_prompt.md`, and saving outputs to
    `folder_path/outputs/{content_type}_outputs/`.

    images_subpath overrides where images are read from (relative to inputs/).
    output_subpath overrides where OCR results are written (relative to outputs/).
    Both are useful when images and outputs live in subfolders (e.g. answer key images
    under exercises/) while the prompt is still keyed by content_type.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder_path}")

    folder_prompt = read_prompt_file(str(folder), content_type)
    out_dir = folder / "outputs" / (output_subpath or f"{content_type}_outputs")
    os.makedirs(out_dir, exist_ok=True)

    images_content_type = images_subpath or content_type
    for img_path in list_image_files(str(folder), images_content_type):
        process_image(img_path, model, folder_prompt, str(out_dir), overwrite=overwrite, content_type=content_type)


def _strip_outer_code_fence(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` or ``` ... ``` fence if the model added one."""
    import re
    return re.sub(r"^```[a-z]*\n([\s\S]*?)\n```$", r"\1", text.strip())


def process_image(img_path: str, model: str, folder_prompt: Optional[str], out_dir: str, overwrite: bool = False, content_type: str = "contents") -> str:
    """Process a single image path and save the raw response to out_dir.

    Returns the saved filepath.
    """
    img_name = os.path.basename(img_path)
    filename = f"raw_response_{os.path.splitext(img_name)[0]}.md"
    out_path = os.path.join(out_dir, filename)

    if not overwrite and os.path.exists(out_path):
        print(f"\nSkipping (already processed): {img_name}")
        return out_path

    print(f"\nProcessing: {img_name}")

    image_b64 = get_optimized_image_b64(img_path)

    if not folder_prompt:
        raise FileNotFoundError(
            f"No prompt.md or prompt.txt found in the image folder. "
            f"Create a prompt file before processing images."
        )
    prompt = folder_prompt

    full_response = ""
    stream = send_streamed_request(model, prompt, [image_b64])
    for tag, payload in stream:
        if tag == "__first_token__":
            print(f"Time to first token: {payload:.2f}s")
        elif tag == "chunk":
            full_response += payload
        elif tag == "__done__":
            print(f"\nTotal Processing Time: {payload:.2f}s")

    full_response = _strip_outer_code_fence(full_response)
    saved = save_raw_response(out_dir, filename, full_response)
    print(f"Saved: {saved}")

    warnings = check_quality(full_response, content_type)
    if warnings:
        print("Quality warnings:")
        for w in warnings:
            print(f"   - {w}")
    else:
        print("Quality check passed.")

    return saved


def run_single_image(image_path: str, model: str, overwrite: bool = False) -> str:
    """Process a single image file.

    Infers content_type from the image's parent folder name (e.g. 'contents' or 'exercises').
    The topic root is three levels up: <topic>/inputs/{content_type}/<image>.
    Prompt is read from <topic>/prompts/{content_type}_prompt.md.
    Output is written to <topic>/outputs/{content_type}_outputs/.
    """
    img = Path(image_path)
    content_type = img.parent.name           # "contents" or "exercises"
    topic_root = img.parent.parent.parent    # <topic>/inputs/{content_type}/
    folder_prompt = read_prompt_file(str(topic_root), content_type)
    out_dir = topic_root / "outputs" / f"{content_type}_outputs"
    os.makedirs(out_dir, exist_ok=True)
    return process_image(str(img), model, folder_prompt, str(out_dir), overwrite=overwrite, content_type=content_type)
