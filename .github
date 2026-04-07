# Copilot Instructions for haiguru

This file provides essential guidance for GitHub Copilot and other AI assistants working in this repository. It summarizes build, test, and lint commands, high-level architecture, and key conventions that are not obvious from a single file.

---

## Build, Test, and Lint Commands

- **Install dependencies:**
  - `uv sync`
- **Start infrastructure:**
  - `docker compose up -d` (Postgres on :5433, pgAdmin on :5050)
- **Apply DB migrations:**
  - `uv run alembic upgrade head`
  - To generate a migration after model changes:
    - `uv run alembic revision --autogenerate -m "describe the change"`
    - `uv run alembic upgrade head`
- **Run all tests:**
  - `uv pip install -e .[dev]` (if not already installed)
  - `pytest`
- **Run a single test file:**
  - `pytest tests/test_glm_ocr_utils.py` (or any test file)

---

## High-Level Architecture

- **Purpose:** Backend for storing and serving educational content and exams. Not related to haisir.
- **Tech stack:** Python 3.11+, SQLAlchemy, Alembic, Docker Compose, Ollama (local LLM/OCR), LlamaIndex, pgvector, pytest.
- **Core modules:**
  - `glm_ocr/`: OCR pipeline (Ollama multimodal, Markdown output)
  - `etl_pipeline/`: ETL for OCR → DB (extract, transform, load)
  - `embed_pipeline/`: Embeds topic_contents into pgvector for hybrid search
  - `rag/`: Hybrid retrieval (dense + sparse) and answer synthesis
  - `db/models.py`: SQLAlchemy models (all PKs are UUID)
  - `llm_factory.py`: LLM/embedding provider routing (Ollama, OpenAI, Anthropic, TogetherAI)
- **Data flow:**
  1. Populate hierarchy from content root (see README for structure)
  2. OCR images → Markdown (`glm_ocr`)
  3. ETL parses Markdown, loads to DB (`etl_pipeline`)
  4. Embedding pipeline stores vectors (`embed_pipeline`)
  5. RAG pipeline retrieves and synthesizes answers (`rag/`)

---

## Key Conventions

- **Content root structure:** Must be exactly 5 levels: `<category>/<grade>/<subject>/<volume>/<topic>`
- **OCR prompts:** Each topic folder must have `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises)
- **Idempotency:** All ETL and embedding steps are safe to re-run (upserts, not inserts)
- **Model selection:** LLM/embedding provider is chosen by prefix (e.g., `openai://gpt-4o`). See `llm_factory.py` and `.env`.
- **Testing:**
  - Tests do not require a running database; `DATABASE_URL` is set to a dummy value in `tests/conftest.py`.
  - External dependencies (Ollama, filesystem) are mocked in tests.
- **DB migrations:** Managed with Alembic. Always run migrations after model changes.
- **Hybrid retrieval:** Dense (HNSW/cosine) + sparse (tsvector/BM25) fused by relative score (not RRF).
- **Query rewriting:** All RAG queries are rewritten and classified for intent/safety before retrieval.
- **All PKs are UUID.**

---

## References
- See `README.md` and `CLAUDE.md` for detailed commands, data model, and pipeline explanations.
- See `db/models.py` for schema details.

---

If you are a Copilot or AI agent, follow these conventions for best results. If you need to add new conventions, update this file.
