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
# --transform-model: override the LLM used to parse exercises (see LLM Providers below)

# Embed all topic_contents into pgvector
uv run python -m embed_pipeline

# Embed a single topic
uv run python -m embed_pipeline --topic-id <uuid>

# RAG query (retrieve + synthesise)
uv run python -m rag "explain integers"
uv run python -m rag "prime numbers" --grade GRADE_7 --subject MATHEMATICS --retrieve-only
```

## RAG Pipeline internals

The `rag` module has three stages:

1. **Query rewriting + intent classification + safety** (`rag/query_rewriter.py`) — one LLM call that returns a `RewriteResult`:
   - `rewritten_query`: keyword-dense version used for retrieval
   - `intent`: `"definition"` | `"computation"` | `"explanation"` — selects synthesis template and is prepended to the original query for synthesis
   - `safe`: `False` if the query is rejected (profanity, prompt injection, harmful content); off-topic benign questions pass through
   - `reject_reason`: friendly message shown to the user when `safe=False`

2. **Hybrid retrieval** (`rag/retriever.py`) — fused dense (HNSW cosine) + sparse (tsvector) search using the rewritten query

3. **Synthesis** (`rag/__main__.py`) — `CompactAndRefine` with an intent-specific prompt template; the synthesiser receives `[intent] original_query` (not the rewritten query) to preserve exact semantic precision

Adding a new intent requires: a new example in `_REWRITE_PROMPT` (query_rewriter.py) and new entries in `_QA_TEMPLATES` and `_REFINE_TEMPLATES` (\_\_main\_\_.py). Unknown intents fall back to `"explanation"`.

Parse errors in the rewriter fail safe — the query is rejected rather than passed through.

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

`glm_ocr/` is a local OCR pipeline that processes textbook images into Markdown using locally-running Ollama multimodal models (default: `glm-ocr-optimized`).

### Pipeline

Sends the image (JPEG-encoded base64) to an Ollama multimodal model using the type-specific prompt. Output saved as `raw_response_<image>.md`.

### Key behaviors

- Each topic folder **must** have `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises) — processing fails without it (`read_prompt_file` in `utils.py`).
- Already-processed images are skipped by default; use `--overwrite` to reprocess.
- `check_quality` in `utils.py` runs heuristic checks on the raw response looking for missing `### CONTENT` section headers and question patterns that indicate the model captured exercises instead of theory content.
- Ollama must be running locally; no API keys needed for OCR.

## LLM Providers

Three pipelines use an LLM. Each supports a provider prefix on the model name:

| Prefix | Provider | Required env var |
|---|---|---|
| *(none)* | Ollama (local, default) | — |
| `openai://` | OpenAI | `OPENAI_API_KEY` |
| `anthropic://` | Anthropic | `ANTHROPIC_API_KEY` |
| `together://` | TogetherAI (OpenAI-compat) | `TOGETHER_API_KEY` |

### Environment variables (`config.py`)

| Variable | Used by | Default |
|---|---|---|
| `TRANSFORM_MODEL` | Exercise parsing LLM | `qwen3.5:9b` (Ollama) |
| `RAG_MODEL` | RAG answer synthesis LLM | `qwen3.5:9b` (Ollama) |
| `EMBED_MODEL` | Embedding model | `BAAI/bge-m3` (HuggingFace local) |
| `OPENAI_API_KEY` | OpenAI calls | — |
| `ANTHROPIC_API_KEY` | Anthropic calls | — |
| `TOGETHER_API_KEY` | TogetherAI calls | — |

### Examples

```bash
# Use GPT-4o to parse exercises
uv run python -m etl_pipeline --topic-path "..." --type exercises --transform-model "openai://gpt-4o"

# Use Claude for RAG synthesis (set in .env)
RAG_MODEL=anthropic://claude-opus-4-5

# Use OpenAI embeddings (also update EMBED_DIM to match, e.g. 3072)
EMBED_MODEL=openai://text-embedding-3-large
EMBED_DIM=3072
```

The `TRANSFORM_MODEL` can also be overridden per-run:
```bash
uv run python -m etl_pipeline --topic-path "..." --type exercises --transform-model "together://meta-llama/Llama-3-70b-chat-hf"
```

Routing logic lives in `llm_factory.py` (LlamaIndex objects for RAG/embed) and `glm_ocr/client.py` (`send_text_request_streaming` for exercise parsing).

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
- Ollama (local) for vision OCR; also supported: OpenAI, Anthropic, TogetherAI for text LLMs
- LlamaIndex for embedding, vector store, and RAG orchestration
- pgvector for dense + sparse hybrid search
