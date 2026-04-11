# ETL Pipeline

Covers loading OCR outputs (contents and/or exercises) into Postgres via `etl_pipeline/`.

## Commands

```bash
# Load contents (default)
uv run python -m etl_pipeline --topic-path "C:/github/siva/SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"

# Load exercises (skip OCR if already done)
uv run python -m etl_pipeline --topic-path "..." --type exercises --skip-extract

# Load both contents and exercises
uv run python -m etl_pipeline --topic-path "..." --type both --skip-extract
```

## Flags

| Flag | Effect |
|---|---|
| `--type` | `contents` (default) \| `exercises` \| `both` |
| `--skip-extract` | Skip OCR; use existing `.md` files in `outputs/` |
| `--skip-load` | OCR only; don't write to DB |
| `--overwrite` | Re-run OCR even if output already exists |
| `--transform-model` | Override the LLM used to parse exercises (see llm_providers.md) |

## Exercise Parsing

Letter-based answers like `(b)` are resolved to option text by `etl_pipeline/parse_exercises.py`.
`options` and `correct_answers` columns are JSONB lists.

## Gotchas

- `--skip-extract` is almost always needed on re-runs; OCR is slow and outputs persist.
- `--type both` with `--skip-extract` is the standard re-load pattern after editing prompts.
- The `--transform-model` flag accepts provider-prefixed model names (see `agent_docs/llm_providers.md`).
