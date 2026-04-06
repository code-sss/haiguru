import argparse
import sys
from .runner import run_on_folder, run_single_image


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m glm_ocr", description="Run OCR on images or folders using glm_ocr package")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder", help="Path to folder containing images to process")
    group.add_argument("--image", help="Path to a single image to process")
    parser.add_argument("--model", default="glm-ocr-optimized", help="Model name to use")
    parser.add_argument("--output-subdir", default="outputs", help="Subfolder name for outputs when processing a folder")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files (default: skip already processed images)")

    args = parser.parse_args(argv)

    if args.folder:
        run_on_folder(args.folder, args.model, output_subdir=args.output_subdir, overwrite=args.overwrite)
    elif args.image:
        saved = run_single_image(args.image, args.model, output_dir=args.output_subdir, overwrite=args.overwrite)
        print(f"Saved: {saved}")


if __name__ == "__main__":
    main()
