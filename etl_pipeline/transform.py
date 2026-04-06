"""Transform step: run OCR on topic images to produce raw_response_*.md files."""

from glm_ocr.runner import run_on_folder
from glm_ocr.utils import list_image_files
from .extract import TopicContext


def transform(
    ctx: TopicContext,
    model: str = "glm-ocr-optimized",
    overwrite: bool = False,
    content_type: str = "contents",
) -> None:
    """Run glm_ocr on images in ctx.topic_path/inputs/{content_type}/.

    Outputs are saved to ctx.outputs_dir/{content_type}_outputs/.
    Skips gracefully if the inputs directory does not exist.
    Skips images that already have output unless overwrite=True.
    """
    inputs_dir = ctx.topic_path / "inputs" / content_type
    if not inputs_dir.is_dir():
        print(f"[Transform] inputs/{content_type}/ not found, skipping.")
        return

    images = list(list_image_files(str(ctx.topic_path), content_type))
    if not images:
        print(f"[Transform] No images found in inputs/{content_type}/, skipping.")
        return

    print(f"\n[Transform] {ctx.topic} ({content_type}) — {len(images)} image(s)")
    run_on_folder(str(ctx.topic_path), model=model, content_type=content_type, overwrite=overwrite)

