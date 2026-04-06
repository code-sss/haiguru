import os
from pathlib import Path
from typing import Optional
from .client import get_optimized_image_b64, send_streamed_request, save_raw_response
from .utils import read_prompt_file, list_image_files, check_quality


def run_on_folder(folder_path: str, model: str, output_subdir: str = "outputs", overwrite: bool = False) -> None:
    """Process all images in `folder_path`, use folder-level prompt if present,
    and save raw responses to `folder_path/<output_subdir>/raw_response_<image>.txt`.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder_path}")

    folder_prompt = read_prompt_file(str(folder))
    out_dir = folder / output_subdir
    os.makedirs(out_dir, exist_ok=True)

    for img_path in list_image_files(str(folder)):
        process_image(img_path, model, folder_prompt, str(out_dir), overwrite=overwrite)


def _strip_outer_code_fence(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` or ``` ... ``` fence if the model added one."""
    import re
    return re.sub(r"^```[a-z]*\n([\s\S]*?)\n```$", r"\1", text.strip())


def process_image(img_path: str, model: str, folder_prompt: Optional[str], out_dir: str, overwrite: bool = False) -> str:
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

    warnings = check_quality(full_response)
    if warnings:
        print("Quality warnings:")
        for w in warnings:
            print(f"   - {w}")
    else:
        print("Quality check passed.")

    return saved


def run_single_image(image_path: str, model: str, output_dir: Optional[str] = None, overwrite: bool = False) -> str:
    """Process a single image file. If a folder-level prompt exists, it will be used.

    The output will be written to `<image_folder>/<output_dir or 'outputs'>/` and the
    saved filepath is returned.
    """
    image_path = str(image_path)
    folder = Path(image_path).parent
    folder_prompt = read_prompt_file(str(folder))
    out_dir = output_dir if (output_dir and os.path.isabs(output_dir)) else os.path.join(str(folder), output_dir or "outputs")
    os.makedirs(out_dir, exist_ok=True)
    return process_image(image_path, model, folder_prompt, out_dir, overwrite=overwrite)
