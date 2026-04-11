# OCR Pipeline (glm_ocr)

Covers the `glm_ocr/` package — processing textbook images into Markdown via a local Ollama multimodal model.

## How It Works

Sends JPEG-encoded base64 images to an Ollama multimodal model (default: `glm-ocr-optimized`)
using a type-specific prompt. Output saved as `raw_response_<image>.md` in the topic's outputs folder.

## Commands

```bash
# Process a folder (contents by default)
uv run python -m glm_ocr --folder <path-to-topic-folder>
uv run python -m glm_ocr --folder <path-to-topic-folder> --type exercises

# Process a single image
uv run python -m glm_ocr --image <path-to-image>
```

Options: `--model`, `--type` (`contents` | `exercises`, default: `contents`), `--overwrite` (default: skip already processed)

## Data Source Layout

Raw content root: `C:/github/siva/SVC/`

```
SVC/
└── GRADE_7/                       ← course_path_node (node_type=grade)
    └── MATHEMATICS/               ← course_path_node (node_type=subject)
        └── VOLUME_1/              ← course_path_node (node_type=course)
            └── INTEGERS/          ← topic
                ├── inputs/
                │   ├── contents/          ← theory images
                │   └── exercises/         ← exercise images
                ├── outputs/
                │   ├── contents_outputs/  ← raw_response_IMG_*.md (→ topic_content rows)
                │   └── exercises_outputs/ ← raw_response_IMG_*.md (→ question rows)
                └── prompts/
                    ├── contents_prompt.md
                    └── exercises_prompt.md
```

## Gotchas

- Each topic folder **must** contain `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises) — `read_prompt_file` in `utils.py` hard-fails without it.
- `check_quality` in `utils.py` runs heuristics looking for missing `### CONTENT` headers and exercise patterns leaking into theory content — check this output if OCR results look wrong.
- Ollama must be running locally; no API keys required for OCR.
- Already-processed images are skipped by default; use `--overwrite` to reprocess.
