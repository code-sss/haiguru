# ETL Pipeline

Covers loading OCR outputs (contents and/or exercises) into Postgres via `etl_pipeline/`.

## Commands

```bash
# Load contents (OCR → transform → DB)
uv run python -m etl_pipeline --topic-path "C:/github/siva/SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS" --etl-contents

# Load exercises via full OCR + LLM pipeline
uv run python -m etl_pipeline --topic-path "..." --etl-exercises

# Load exercises from JSON — topic path derives course node + topic automatically
uv run python -m etl_pipeline --load-exercises qa-sample.json --topic-path "..."

# Load exercises from JSON — course node by UUID, no topic
uv run python -m etl_pipeline --load-exercises qa-sample.json --course-node-id <uuid>

# Load exercises from JSON — course node by UUID + link questions to existing topic
uv run python -m etl_pipeline --load-exercises qa-sample.json --course-node-id <uuid> --topic-id <uuid>

# Load both contents and exercises from existing OCR output
uv run python -m etl_pipeline --topic-path "..." --etl-contents --etl-exercises --skip-extract
```

## Flags

| Flag | Effect |
|---|---|
| `--etl-contents` | Run full extract→transform→load for contents |
| `--etl-exercises` | Run full extract→transform→load for exercises (OCR + LLM) |
| `--load-exercises <file>` | Load exercises + create exam template from a JSON file; bypasses extract + transform |
| `--course-node-id <uuid>` | `course_path_node` for the exam template (used with `--load-exercises`) |
| `--topic-id <uuid>` | Optional topic to link questions to (used with `--load-exercises + --course-node-id`) |
| `--created-by <uuid>` | Written to `exam_template.created_by` (default: system UUID) |
| `--topic-path` | Required for `--etl-*`; also accepted by `--load-exercises` to derive course node + topic |
| `--skip-extract` | Skip OCR; use existing `.md` files in `outputs/` (applies to `--etl-*` flags) |
| `--skip-load` | OCR + transform only; don't write to DB |
| `--overwrite` | Re-run OCR even if output already exists |
| `--transform-model` | Override the LLM used to parse exercises (see llm_providers.md) |

## JSON exercises format (`--load-exercises`)

The JSON file must have an `items` array. Each item is either a standalone question (`type: "question"`)
or a paragraph with nested questions (`type: "paragraph"`):

- `options` — list of `{id, text}` objects; normalized to plain strings on load
- `correct_answers` — letter IDs (e.g. `"c"`) or plain text; letter IDs are resolved to option text
- Paragraph items carry `content` (passage text) and `title`; nested questions are flattened and linked via `paragraph_questions`
- Top-level `title`, `description`, `passing_score`, `duration_minutes` become the `exam_template` row
- `passing_score` > 1 is treated as a percentage and converted (e.g. `80` → `0.8`)
- `mode` defaults to `"static"` if not present in the JSON

## Exercise Parsing (OCR path)

Each `exercises_outputs/raw_response_*.md` file is sent to an LLM (`TRANSFORM_MODEL`) which returns
a structured JSON array of questions. `options` and `correct_answers` are JSONB lists of plain strings.

## Gotchas

- `--skip-extract` is almost always needed on re-runs; OCR is slow and outputs persist.
- `--etl-contents --etl-exercises --skip-extract` is the standard re-load pattern after editing prompts.
- The `--transform-model` flag accepts provider-prefixed model names (see `agent_docs/llm_providers.md`).
- At least one of `--etl-contents`, `--etl-exercises`, or `--load-exercises` must be provided.
