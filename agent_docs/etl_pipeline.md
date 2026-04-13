# ETL Pipeline

Covers loading OCR outputs (contents and/or exercises) into Postgres via `etl_pipeline/`.

## Pipeline stages

```
images → [extract] → .md files → [transform] → JSON file → [load] → DB
```

Each stage can be skipped independently:

| Skip flag | Skips | Leaves |
|---|---|---|
| `--skip-extract` | OCR step | existing `.md` files used |
| `--skip-transform` | LLM parse step | existing `.md` files untouched, no JSON written |
| `--skip-load` | DB write step | intermediary JSON written but not loaded |

## Commands

```bash
# Full pipeline: OCR → transform → load (contents)
uv run python -m etl_pipeline --topic-path "C:/github/siva/SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS" --etl-contents

# Full pipeline: OCR → transform → load (exercises)
uv run python -m etl_pipeline --topic-path "..." --etl-exercises

# Step 1 only — OCR, inspect .md files before doing anything else
uv run python -m etl_pipeline --topic-path "..." --etl-exercises --skip-transform --skip-load

# Step 2 only — transform existing .md files, inspect exercises.json
uv run python -m etl_pipeline --topic-path "..." --etl-exercises --skip-extract --skip-load

# Step 3 only — reload from saved exercises.json (after editing it)
uv run python -m etl_pipeline --load-exercises "outputs/exercises_outputs/exercises.json" --topic-path "..."

# Re-run transform + load on existing .md files (skip OCR)
uv run python -m etl_pipeline --topic-path "..." --etl-contents --etl-exercises --skip-extract

# Load exercises from a hand-authored JSON — topic path derives course node + topic
uv run python -m etl_pipeline --load-exercises qa-sample.json --topic-path "..."

# Load exercises from JSON — course node by UUID, no topic
uv run python -m etl_pipeline --load-exercises qa-sample.json --course-node-id <uuid>

# Load exercises from JSON — course node by UUID + link questions to existing topic
uv run python -m etl_pipeline --load-exercises qa-sample.json --course-node-id <uuid> --topic-id <uuid>
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
| `--skip-extract` | Skip OCR; use existing `.md` files in `outputs/` |
| `--skip-transform` | Skip LLM parse step; no JSON written (use with `--skip-load` for OCR-only) |
| `--skip-load` | OCR + transform only; don't write to DB |
| `--overwrite` | Re-run OCR even if output already exists |
| `--transform-model` | Override the LLM used to parse exercises (see llm_providers.md) |

## Intermediary outputs

Both content types now write a JSON file after transform, alongside the `.md` files:

| File | Written by | Format |
|---|---|---|
| `outputs/contents_outputs/contents.json` | `--etl-contents` transform | `[{title, text, order}]` |
| `outputs/exercises_outputs/exercises.json` | `--etl-exercises` transform | qa-sample.json format (see below) |

`exercises.json` is in the same format as a hand-authored qa-sample.json, so it can be fed directly
to `--load-exercises` to reload without re-running OCR or the LLM transform. This is useful for:
- Inspecting what the LLM extracted before committing to DB
- Manually editing questions/answers then reloading
- Re-loading after a DB wipe without re-running OCR

## JSON exercises format (qa-sample.json)

Used by both `--load-exercises` and the saved `exercises.json` intermediary:

```json
{
  "version": 2,
  "title": "...",
  "description": "...",
  "passing_score": 80,
  "duration_minutes": 45,
  "items": [
    {
      "type": "question",
      "question_type": "single_choice|multiple_choice|true_false|fill_in_the_blank|essay",
      "question_text": "...",
      "options": [{"id": "a", "text": "..."}, {"id": "b", "text": "..."}],
      "correct_answers": ["a"],
      "explanation": "...",
      "difficulty": "easy|medium|hard",
      "tags": ["..."]
    },
    {
      "type": "paragraph",
      "title": "...",
      "content": "<passage text>",
      "questions": [ ... ]
    }
  ]
}
```

- `options` — `{id, text}` objects; normalized to plain strings on load
- `correct_answers` — option IDs (e.g. `"a"`, `"c"`); resolved to option text on load
- `passing_score` > 1 treated as percentage (`80` → `0.8`)
- `mode` defaults to `"static"` if absent
- Paragraph `questions` are flattened and linked via `paragraph_questions` table

## Exercise Parsing (OCR path)

Each `exercises_outputs/raw_response_*.md` file is sent to the LLM (`TRANSFORM_MODEL`) which returns
items in qa-sample.json format (structured `{id, text}` options, ID-based correct_answers, explanation,
difficulty, tags, and paragraph/passage support). The combined result is saved to `exercises.json`
before being normalized for the load step.

## Gotchas

- `--skip-extract` is almost always needed on re-runs; OCR is slow and outputs persist.
- `--etl-contents --etl-exercises --skip-extract` is the standard re-load pattern after editing prompts.
- The `--transform-model` flag accepts provider-prefixed model names (see `agent_docs/llm_providers.md`).
- At least one of `--etl-contents`, `--etl-exercises`, or `--load-exercises` must be provided.
- `exercises.json` is overwritten each time transform runs; back it up before editing if you need to preserve manual changes.
