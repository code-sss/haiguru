# CLAUDE.md

`haiguru` — standalone backend for educational content and exams.
IMPORTANT: This is NOT the haisir project. Schema was inspired by haisir but haiguru is fully independent.

## Essential Commands

```bash
# First-time setup
docker compose up -d
cp .env.example .env
uv sync
uv run alembic upgrade head

# After changing db/models.py
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head

# Embed content into pgvector
uv run python -m embed_pipeline

# RAG query
uv run python -m rag "explain integers"

# Grade a completed exam session
uv run python -m eval_pipeline --session-id <uuid>
```

## Directory Map

```
db/models.py          ← SQLAlchemy schema (all tables)
config.py             ← env var definitions
llm_factory.py        ← LLM provider routing (RAG/embed)
reranker_factory.py   ← Reranker provider routing
glm_ocr/              ← OCR pipeline (images → Markdown via Ollama)
etl_pipeline/         ← Load OCR outputs into Postgres
embed_pipeline/       ← Embed topic_contents into pgvector
rag/                  ← 4-stage RAG pipeline
eval_pipeline/        ← Grade exam sessions (OCR + objective + LLM essay judge)
agent_docs/           ← Task-specific reference docs (see below)
```

## Non-Default Conventions

- Postgres runs on **port 5433** (not 5432) to avoid local conflicts
- All primary keys are **UUID**
- LLM models use a provider prefix: `openai://`, `anthropic://`, `together://` (plain = Ollama local)
- `DATABASE_URL` is read from `.env` via `config.py`

## Infrastructure

- pgAdmin: `http://localhost:5050` — `admin@haiguru.com` / `admin`
- DB: `haiguru_db`, user: `haiguru`, pass: `haiguru_pass`
- Docker network: `haiguru-net`; internal host for pgAdmin connections: `haiguru-postgres:5432`

## Reference Docs

| File | Read when |
|---|---|
| `@agent_docs/data_model.md` | Modifying schema, writing migrations, querying tables |
| `@agent_docs/rag_pipeline.md` | Modifying `rag/`, adding intents, debugging retrieval |
| `@agent_docs/llm_providers.md` | Changing models, adding provider support, configuring `.env` |
| `@agent_docs/etl_pipeline.md` | Loading content/exercises into DB, understanding ETL flags |
| `@agent_docs/ocr_pipeline.md` | Running/modifying `glm_ocr/`, debugging OCR failures |
