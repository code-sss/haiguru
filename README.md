# haiguru

Backend for storing and serving educational content and exams.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs Postgres + pgAdmin |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python package manager |
| [Ollama](https://ollama.com/) | Local LLM for OCR (ETL) and answer synthesis (RAG) |

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

### Expected folder structure

The ETL pipeline expects source content rooted at a content root directory with exactly this layout:

```
<content-root>/                     ← passed to populate_hierarchy.py as --content-root
└── <CATEGORY>/                     ← maps to: categories.name
    └── <GRADE>/                    ← maps to: course_path_nodes (node_type=grade)
        └── <SUBJECT>/              ← maps to: course_path_nodes (node_type=subject)
            └── <VOLUME>/           ← maps to: course_path_nodes (node_type=course)
                └── <TOPIC>/        ← maps to: topics.title
                    ├── inputs/
                    │   ├── contents/               ← theory images (never loaded into DB)
                    │   │   └── IMG_*.jpg
                    │   └── exercises/              ← exercise images (never loaded into DB)
                    │       └── IMG_*.jpg
                    ├── outputs/
                    │   ├── contents_outputs/       ← topic_contents (content_type=text), one per page
                    │   │   └── raw_response_IMG_*.md
                    │   └── exercises_outputs/      ← exercise OCR outputs
                    │       └── raw_response_IMG_*.md
                    └── prompts/
                        ├── contents_prompt.md      ← required before running OCR on contents
                        └── exercises_prompt.md     ← required before running OCR on exercises
```

**Example with real data:**

```
C:/github/siva/SVC/
└── SVC/   ← this is the category (the content root's direct child)
    └── GRADE_7/
        └── MATHEMATICS/
            └── VOLUME_1/
                └── INTEGERS/
                    ├── inputs/
                    │   ├── contents/
                    │   │   ├── IMG_0001.jpg
                    │   │   └── IMG_0002.jpg
                    │   └── exercises/
                    │       └── IMG_0003.jpg
                    ├── outputs/
                    │   ├── contents_outputs/
                    │   │   ├── raw_response_IMG_0001.md
                    │   │   └── raw_response_IMG_0002.md
                    │   └── exercises_outputs/
                    │       └── raw_response_IMG_0003.md
                    └── prompts/
                        ├── contents_prompt.md
                        └── exercises_prompt.md
```

**Rules enforced by `etl_pipeline/extract.py`:**
- The topic path must be exactly 5 levels deep: `<category>/<grade>/<subject>/<volume>/<topic>`
- `prompts/contents_prompt.md` must exist before running OCR on contents; `exercises_prompt.md` for exercises
- Images are discovered by extension (`.jpg`, `.jpeg`, `.png`) inside `inputs/contents/` or `inputs/exercises/`
- Already-processed images are skipped unless `--overwrite` is passed
- Output directories are created automatically if they do not exist

### Step 1 — Populate hierarchy

Upserts `categories`, `course_path_nodes`, and `topics` from the content root folder structure. No content or OCR needed. Safe to re-run.

```bash
uv run python populate_hierarchy.py --content-root C:/github/siva/SVC
```

### Step 2 — Load topic content and exercises (OCR → DB)

Runs OCR on images and loads the resulting `.md` files into DB tables. Use `--type` to control what is processed:

| `--type` | OCR source | Loaded into |
|---|---|---|
| `contents` (default) | `inputs/contents/` | `topic_contents` |
| `exercises` | `inputs/exercises/` | `questions`, `paragraph_questions` |
| `both` | both | all of the above |

```bash
# Full run (OCR + load) — theory content only
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"

# Load exercises (OCR already done)
uv run python -m etl_pipeline --topic-path "..." --type exercises --skip-transform

# Load both contents and exercises from existing OCR output
uv run python -m etl_pipeline --topic-path "..." --type both --skip-transform

# OCR both types, then load exercises only
uv run python -m etl_pipeline --topic-path "..." --type exercises

# OCR only — inspect output before loading
uv run python -m etl_pipeline --topic-path "..." --skip-load

# Re-process all images (overwrite existing .md files)
uv run python -m etl_pipeline --topic-path "..." --overwrite
```

**Exercises format:** Each `exercises_outputs/raw_response_*.md` file must use structured markers (`### QUESTION`, `### PARAGRAPH`) — see `etl_pipeline/parse_exercises.py`. Letter-based answers like `(b)` are resolved to option text automatically. Sub-questions under a `### PARAGRAPH` are linked via a `paragraph_questions` row.

**Prerequisites for OCR:** Ollama must be running with the `glm-ocr-optimized` model pulled, and the topic folder must have `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises).

### Step 3 — Generate embeddings

Reads all `topic_contents` rows from Postgres, generates embeddings using `BAAI/bge-m3`, and stores vectors in the `topic_content_vectors` table (managed by pgvector, not Alembic).

```bash
# Embed all content
uv run python -m embed_pipeline

# Embed a single topic
uv run python -m embed_pipeline --topic-id <uuid>
```

Re-running is safe — existing nodes are updated, not duplicated.

The embed pipeline stores vectors with `hybrid_search=True`, which adds a `text_search_tsv` tsvector column alongside the dense embeddings — required for the hybrid retriever.

### Step 4 — Query with the hybrid RAG pipeline

The `rag` module combines dense vector search (HNSW cosine) and sparse full-text search (tsvector / BM25), fuses results with relative-score re-ranking, and optionally synthesises an answer via Ollama.

```bash
# Full Q&A — retrieve + synthesise with qwen3.5:9b
uv run python -m rag "explain integers"

# Apply metadata filters to scope results
uv run python -m rag "what is a prime number" --grade GRADE_7 --subject MATHEMATICS
uv run python -m rag "addition rules" --course VOLUME_1 --top-k 8

# Repeat a flag for OR semantics within that field
uv run python -m rag "integers" --grade GRADE_7 --grade GRADE_8
# → results matching (grade=GRADE_7 OR grade=GRADE_8)

# Mix AND across fields with OR within a field
uv run python -m rag "integers" --grade GRADE_7 --grade GRADE_8 --subject MATHEMATICS
# → (grade=GRADE_7 OR grade=GRADE_8) AND subject=MATHEMATICS

# Skip LLM synthesis — just show retrieved chunks
uv run python -m rag "fractions" --retrieve-only

# Filter by a specific topic UUID
uv run python -m rag "negative numbers" --topic-id <uuid>
```

The LLM model defaults to `qwen3.5:9b` (set `LLM_MODEL` in `.env` to override). Ollama must be running for synthesis; `--retrieve-only` works without it.

`rag.retriever.build_retriever()` is also importable for use in other parts of the project.

---

## Common scenarios

### New topic — first time

```bash
# Load theory content
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"
# Load exercises
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS" --type exercises --skip-transform
uv run python -m embed_pipeline --topic-id <uuid>
```

### DB was wiped — reload everything

```bash
uv run alembic upgrade head
uv run python populate_hierarchy.py --content-root C:/github/siva/SVC
uv run python -m etl_pipeline --topic-path "..." --skip-transform   # repeat per topic
uv run python -m embed_pipeline
```

### Re-process a bad OCR result

Delete the bad `.md` file and re-run (only the missing file is regenerated):

```bash
rm "SVC/.../outputs/contents_outputs/raw_response_IMG_001.md"
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
| `topic_contents` | `etl_pipeline --type contents` — one row per `.md` file |
| `questions` | `etl_pipeline --type exercises` — one row per parsed question |
| `paragraph_questions` | `etl_pipeline --type exercises` — one per passage, references question UUIDs |
| `topic_content_vectors` | `embed_pipeline` — pgvector table, not Alembic-managed |

All write operations are upserts — re-running any step is always safe.
