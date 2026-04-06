"""Transform step: run OCR on topic images to produce raw_response_*.md files."""

from glm_ocr.runner import run_on_folder
from .extract import TopicContext


def transform(ctx: TopicContext, model: str = "glm-ocr-optimized", overwrite: bool = False) -> None:
    """Run glm_ocr on all images in ctx.topic_path.

    Outputs are saved to ctx.outputs_dir/raw_response_<image>.md.
    Skips images that already have output unless overwrite=True.
    """
    if not ctx.image_paths:
        print(f"No images found in {ctx.topic_path}, skipping transform.")
        return

    print(f"\n[Transform] {ctx.topic} — {len(ctx.image_paths)} image(s)")
    run_on_folder(str(ctx.topic_path), model=model, overwrite=overwrite)
