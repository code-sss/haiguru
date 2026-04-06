# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`haiguru` is a standalone backend for storing and serving educational content and exams.
It is **not** related to the haisir project. The data model was inspired by haisir's schema
but this project is independent.

## Commands

```bash
# Start Postgres + pgAdmin
docker compose up -d

# Copy and edit environment variables (first time only)
cp .env.example .env

# Install dependencies
uv sync

# Apply migrations (run once after docker compose up, and after any model changes)
uv run alembic upgrade head

# Run OCR on a folder of images (default: contents)
uv run python -m glm_ocr --folder <path-to-topic-folder>
uv run python -m glm_ocr --folder <path-to-topic-folder> --type exercises

# Run OCR on a single image
uv run python -m glm_ocr --image <path-to-image>

# OCR options: --model, --type (contents|exercises, default: contents), --overwrite (default: skip already processed)

# ETL pipeline — load contents (default) or exercises into Postgres
uv run python -m etl_pipeline --topic-path "C:/github/siva/SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"
uv run python -m etl_pipeline --topic-path "..." --type exercises --skip-extract
uv run python -m etl_pipeline --topic-path "..." --type both --skip-extract
# --type: contents (default) | exercises | both
# --skip-extract: skip OCR, use existing .md files
# --skip-load: OCR only, don't write to DB
# --overwrite: re-run OCR even if output already exists

# Embed all topic_contents into pgvector
uv run python -m embed_pipeline

# Embed a single topic
uv run python -m embed_pipeline --topic-id <uuid>
```

## Infrastructure

- **Postgres** is exposed on `localhost:5433` (not 5432, to avoid local conflicts)
- **pgAdmin** is at `http://localhost:5050`
  - Email: `admin@haiguru.com` / Password: `admin`
  - Connect to server: host=`haiguru-postgres`, port=`5432`, user=`haiguru`, password=`haiguru_pass`
- Both run in Docker network `haiguru-net`
- Database: `haiguru_db`, user: `haiguru`, password: `haiguru_pass`
- `DATABASE_URL` is read from `.env` via `config.py`

## Data Source

Raw content lives in `C:/github/siva/SVC/` with this directory structure:

```
SVC/                          ← category name
└── GRADE_7/                  ← course_path_node (node_type=grade)
    └── MATHEMATICS/          ← course_path_node (node_type=subject)
        └── VOLUME_1/         ← course_path_node (node_type=course)
            └── INTEGERS/     ← topic
                ├── inputs/
                │   ├── contents/               ← theory images (not loaded into DB)
                │   │   └── IMG_*.jpg
                │   └── exercises/              ← exercise images (not loaded into DB)
                │       └── IMG_*.jpg
                ├── outputs/
                │   ├── contents_outputs/       ← topic_content (content_type=text), one per page
                │   │   └── raw_response_IMG_*.md
                │   └── exercises_outputs/      ← exercise OCR outputs
                │       └── raw_response_IMG_*.md
                └── prompts/
                    ├── contents_prompt.md      ← required before running OCR on contents
                    └── exercises_prompt.md     ← required before running OCR on exercises
```

## glm_ocr Package

`glm_ocr/` is a local OCR pipeline that processes textbook images into Markdown using locally-running Ollama models. It is **not** listed in `pyproject.toml` dependencies — it requires `Pillow`, `ollama`, and `requests` separately.

### Pipeline

Sends the image (JPEG-encoded base64) to an Ollama multimodal model (default: `glm-ocr-optimized`) using the type-specific prompt. Output saved as `raw_response_<image>.md`.

### Key behaviors

- Each topic folder **must** have `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises) — processing fails without it (`read_prompt_file` in `utils.py`).
- Already-processed images are skipped by default; use `--overwrite` to reprocess.
- `check_quality` in `utils.py` runs heuristic checks on the raw response looking for missing `### CONTENT` section headers and question patterns that indicate the model captured exercises instead of theory content.
- Ollama must be running locally; no API keys or environment variables are needed.

## Data Model

Tables are defined in `db/models.py` using SQLAlchemy declarative style.
Schema is managed via Alembic — after changing models, run:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

### Table hierarchy

```
categories
  └── course_path_nodes  (self-referential: grade → subject → course)
        └── topics
              └── topic_contents   (text pages from raw_response_*.md)
              └── questions        (exercises extracted from content)
                    └── paragraph_questions  (grouped questions under a passage)

exam_templates  (linked to a course_path_node)
  └── exam_template_questions  (questions in the template)

exam_sessions   (a user's attempt at an exam_template)
  └── exam_session_questions
  └── answers
```

### Key column notes

- All primary keys are UUID.
- `course_path_nodes.node_type`: `grade` | `subject` | `course`
- `topic_contents.content_type`: `video` | `pdf` | `text` | `question` | `question_answer`
- `questions.question_type`: `single_choice` | `multiple_choice` | `true_false` | `fill_in_the_blank` | `essay` | `paragraph`
- `questions.options` and `correct_answers` are JSONB lists. Letter-based answers like `(b)` are resolved to option text by `etl_pipeline/parse_exercises.py`.
- `paragraph_questions.question_ids`: `UUID[]` — ordered list of `questions.id` values that belong to this passage.
- `exam_templates.mode`: `static` | `dynamic` | `custom`
- `exam_sessions.status`: `pending` | `ongoing` | `completed` | `failed`
- `user_id` / `created_by` fields store a string (Keycloak `sub` claim or a plain user identifier — TBD).
- `ExamTemplate` has CHECK constraints: `duration_minutes > 0` and `passing_score` in `[0.0, 1.0]`.

## Tech Stack

- Python 3.11+, managed with `uv`
- SQLAlchemy 2.x (sync, declarative)
- psycopg2-binary for Postgres driver
- Docker Compose for local infrastructure
- Ollama (local) for OCR and formatting models
