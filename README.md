# haiguru

Backend for storing and serving educational content and exams.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs Postgres + pgAdmin |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python package manager |
| [Ollama](https://ollama.com/) | Local LLM for OCR (needed for ETL only) |

---

## From-scratch setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd haiguru
cp .env.example .env   # edit if your DB port or credentials differ
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Start Postgres + pgAdmin

```bash
docker compose up -d
```

- Postgres: `localhost:5433`
- pgAdmin: `http://localhost:5050` — `admin@haiguru.com` / `admin`
  - Connect to server: host=`haiguru-postgres`, port=`5432`, user=`haiguru`, password=`haiguru_pass`

The container uses the `pgvector/pgvector:pg16` image and auto-runs `db/init/01_extensions.sql` on first start, which enables the `vector` extension needed for embeddings.

### 4. Apply database migrations

```bash
uv run alembic upgrade head
```

This creates all tables (`categories`, `course_path_nodes`, `topics`, `topic_contents`, `questions`, `exam_templates`, etc.).

> After changing `db/models.py`, generate and apply a new migration:
> ```bash
> uv run alembic revision --autogenerate -m "describe the change"
> uv run alembic upgrade head
> ```

---

## Data pipeline

```
SVC/<category>/<grade>/<subject>/<volume>/<topic>/
    inputs/   ← source images
    outputs/  ← OCR output (.md files, one per image)
    prompts/  ← prompt.md required by OCR model
```

### Step 1 — Populate hierarchy

Upserts `categories`, `course_path_nodes`, and `topics` from the SVC folder structure. No content or OCR needed. Safe to re-run.

```bash
uv run python populate_hierarchy.py --svc-root C:/github/siva/SVC
```

### Step 2 — Load topic content (OCR → DB)

Runs OCR on images in a topic folder and loads the resulting `.md` files into `topic_contents`.

```bash
# Full run: OCR + load
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"

# Skip OCR (outputs/ already exist), just load into DB
uv run python -m etl_pipeline --topic-path "..." --skip-transform

# OCR only — inspect output before loading
uv run python -m etl_pipeline --topic-path "..." --skip-load

# Re-process all images (overwrite existing .md files)
uv run python -m etl_pipeline --topic-path "..." --overwrite
```

**Prerequisites for OCR:** Ollama must be running with the `glm-ocr-optimized` model pulled, and the topic folder must have a `prompts/prompt.md`.

### Step 3 — Generate embeddings

Reads all `topic_contents` rows from Postgres, generates embeddings using `BAAI/bge-m3`, and stores vectors in the `topic_content_vectors` table (managed by pgvector, not Alembic).

```bash
# Embed all content
uv run python -m embed_pipeline

# Embed a single topic
uv run python -m embed_pipeline --topic-id <uuid>
```

Re-running is safe — existing nodes are updated, not duplicated.

---

## Common scenarios

### New topic — first time

```bash
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"
uv run python -m embed_pipeline --topic-id <uuid>
```

### DB was wiped — reload everything

```bash
uv run alembic upgrade head
uv run python populate_hierarchy.py --svc-root C:/github/siva/SVC
uv run python -m etl_pipeline --topic-path "..." --skip-transform   # repeat per topic
uv run python -m embed_pipeline
```

### Re-process a bad OCR result

Delete the bad `.md` file and re-run (only the missing file is regenerated):

```bash
rm "SVC/.../outputs/raw_response_IMG_001.md"
uv run python -m etl_pipeline --topic-path "..."
uv run python -m embed_pipeline --topic-id <uuid>
```

Or re-process all images in a topic:

```bash
uv run python -m etl_pipeline --topic-path "..." --overwrite
uv run python -m embed_pipeline --topic-id <uuid>
```

---

## What's in the database

| Table | Written by |
|---|---|
| `categories` | `populate_hierarchy.py` (also ETL as safety net) |
| `course_path_nodes` | `populate_hierarchy.py` (also ETL as safety net) |
| `topics` | `populate_hierarchy.py` (also ETL as safety net) |
| `topic_contents` | `etl_pipeline` — one row per `.md` file |
| `topic_content_vectors` | `embed_pipeline` — pgvector table, not Alembic-managed |

All write operations are upserts — re-running any step is always safe.
