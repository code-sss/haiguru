# haiguru

Backend for storing and serving educational content and exams.

## Infrastructure

Start Postgres and pgAdmin:

```bash
docker compose up -d
uv run alembic upgrade head         # run once to create tables (repeat after model changes)
```

- Postgres: `localhost:5433`
- pgAdmin: `http://localhost:5050` — `admin@haiguru.com` / `admin`

## ETL Pipeline

Content flows from raw images into Postgres in three steps:

```
images in topic folder
    ↓  [Transform]  glm_ocr — OCR each image via Ollama
    ↓               saves outputs/raw_response_<image>.md
    ↓  [Load]       reads .md files, upserts into Postgres:
    ↓               category → grade → subject → volume → topic → topic_contents
```

The folder path encodes the full hierarchy — no extra config needed:

```
<category>/<grade>/<subject>/<volume>/<topic>/
    e.g. SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS/
```

### Prerequisites

- Ollama running locally with `glm-ocr-optimized` model pulled
- A `prompt.md` or `prompt.txt` in the topic folder (instructs the OCR model)
- Postgres running (`docker compose up -d`) with tables created

### What gets written to Postgres

| Table | Rows |
|---|---|
| `categories` | one row per root folder (e.g. SVC), created on first run |
| `course_path_nodes` | one row each for grade, subject, volume, created on first run |
| `topics` | one row per topic folder, created on first run |
| `topic_contents` | one row per `.md` file (`content_type=text`), upserted on every run |

All rows are upserted — re-running the pipeline is always safe.

---

## Scenarios

### 1. New topic — first time

Images are in the topic folder, nothing in DB yet.

```bash
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"
```

Runs OCR on all images → saves `.md` files → creates all hierarchy rows → inserts all `topic_contents` rows.

---

### 2. New topic — OCR already done, just load into DB

`.md` files already exist in `outputs/`, DB has no rows for this topic yet.

```bash
uv run python -m etl_pipeline --topic-path "..." --skip-transform
```

Skips OCR → creates hierarchy rows → inserts `topic_contents` rows.

---

### 3. Append new images to an existing topic

New images added to a topic folder that is already loaded in the DB.

```bash
uv run python -m etl_pipeline --topic-path "..."
```

OCR skips already-processed images (no `--overwrite`) → new `.md` files are created → load inserts new `topic_contents` rows → existing rows are untouched.

---

### 4. Re-process a bad image (OCR quality was poor)

One image produced a bad `.md` file. Fix the `prompt.md` or retry with a different model.

```bash
uv run python -m etl_pipeline --topic-path "..." --overwrite
```

Re-runs OCR on all images (overwriting existing `.md` files) → load updates all `topic_contents` rows with new text.

To re-process a single image, delete its `raw_response_*.md` file and run without `--overwrite` — only the missing file will be regenerated.

---

### 5. OCR only — review output before loading

Run OCR and inspect the `.md` files before committing anything to the DB.

```bash
uv run python -m etl_pipeline --topic-path "..." --skip-load
```

---

### 6. Reload DB from existing `.md` files (e.g. after DB reset)

`.md` files exist, DB is empty or was wiped.

```bash
uv run python -m etl_pipeline --topic-path "..." --skip-transform
```

Same as scenario 2 — hierarchy and content rows are recreated from the `.md` files.
