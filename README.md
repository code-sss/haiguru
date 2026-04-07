# haiguru

Backend for storing and serving educational content and exams.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs Postgres + pgAdmin |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python package manager |
| [Ollama](https://ollama.com/) | Vision OCR model (required for OCR step); also used as default LLM for exercise parsing and RAG — can be replaced by OpenAI / Anthropic / TogetherAI |

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

**Rules enforced by the ETL pipeline:**
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

Runs OCR on images (extract), reads and parses the `.md` files via an LLM (transform), then loads into DB tables (load). Use `--type` to control what is processed:

| `--type` | OCR source | Loaded into |
|---|---|---|
| `contents` (default) | `inputs/contents/` | `topic_contents` |
| `exercises` | `inputs/exercises/` | `questions`, `paragraph_questions` |
| `both` | both | all of the above |

```bash
# Full run (OCR + load) — theory content only
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"

# Load exercises (OCR already done)
uv run python -m etl_pipeline --topic-path "..." --type exercises --skip-extract

# Load both contents and exercises from existing OCR output
uv run python -m etl_pipeline --topic-path "..." --type both --skip-extract

# OCR both types, then load exercises only
uv run python -m etl_pipeline --topic-path "..." --type exercises

# OCR only — inspect output before loading
uv run python -m etl_pipeline --topic-path "..." --skip-load

# Re-process all images (overwrite existing .md files)
uv run python -m etl_pipeline --topic-path "..." --overwrite
```

**Exercises parsing:** Each `exercises_outputs/raw_response_*.md` file is sent to an LLM (`TRANSFORM_MODEL`, default `qwen3.5:9b` via Ollama) which returns a structured JSON array of questions. No fixed markers are required in the OCR output. See `etl_pipeline/llm_transform_exercises.py` and the [LLM Providers](#llm-providers) section for how to use a different model.

**Prerequisites for OCR:** Ollama must be running with the `glm-ocr-optimized` model pulled, and the topic folder must have `prompts/contents_prompt.md` (and `exercises_prompt.md` for exercises).

### Step 3 — Generate embeddings

Reads all `topic_contents` rows from Postgres, generates embeddings, and stores vectors in the `topic_content_vectors` table (managed by pgvector, not Alembic).

Default model: `BAAI/bge-m3` (HuggingFace, runs locally). Override via `EMBED_MODEL` in `.env` — see [LLM Providers](#llm-providers).

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

The LLM model for synthesis defaults to `qwen3.5:9b` via Ollama (set `RAG_MODEL` in `.env` to override — see [LLM Providers](#llm-providers) for OpenAI/Anthropic/TogetherAI options). Ollama must be running for synthesis; `--retrieve-only` works without it.

`rag.retriever.build_retriever()` is also importable for use in other parts of the project.

---

## LLM Providers

Three pipelines support pluggable LLM/embedding providers via a prefix on the model name:

| Prefix | Provider | Required env var |
|---|---|---|
| *(none)* | Ollama (local, **default**) for LLM; HuggingFace (local) for embeddings | — |
| `openai://` | OpenAI | `OPENAI_API_KEY` |
| `anthropic://` | Anthropic | `ANTHROPIC_API_KEY` |
| `together://` | TogetherAI (OpenAI-compatible) | `TOGETHER_API_KEY` |

Set the key(s) in `.env`, then point the model variable at the provider:

```ini
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
TOGETHER_API_KEY=...

# Use GPT-4o for exercise parsing and RAG synthesis
TRANSFORM_MODEL=openai://gpt-4o
RAG_MODEL=openai://gpt-4o

# Use OpenAI embeddings (update EMBED_DIM to match the model)
EMBED_MODEL=openai://text-embedding-3-large
EMBED_DIM=3072
```

`TRANSFORM_MODEL` can also be overridden per-run without changing `.env`:

```bash
uv run python -m etl_pipeline --topic-path "..." --type exercises \
  --transform-model "anthropic://claude-opus-4-5"
```

> **Note:** Ollama is still required for vision OCR (`glm-ocr-optimized`). Only the text LLM and embedding steps support external providers.

---

### New topic — first time

```bash
# Load theory content
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS"
# Load exercises
uv run python -m etl_pipeline --topic-path "SVC/GRADE_7/MATHEMATICS/VOLUME_1/INTEGERS" --type exercises --skip-extract
uv run python -m embed_pipeline --topic-id <uuid>
```

### DB was wiped — reload everything

```bash
uv run alembic upgrade head
uv run python populate_hierarchy.py --content-root C:/github/siva/SVC
uv run python -m etl_pipeline --topic-path "..." --skip-extract   # repeat per topic
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

---

## Technical Details

### RAG Pipeline
is the code doing 
1. hybrid search? what type of hybrid search? what is the weighting (beta or k in Reciprocal Rank Fusion)?
2. Is the database using HNSW or similar indexing?
3. What chunking strategy is used?
4. Is there query rewriting of input prompt? GLINER or HyDE
5. Are we doing Reranking after retrieval?
6. What temparature, top k, top p, repitition penalties, logit biases and other LLM parameters are used?

#### 1. Hybrid Search

Yes — dense + sparse, fused via **Relative Score Fusion (RSF)**.

| Leg | Method |
|---|---|
| Dense | Cosine similarity over HNSW vector index |
| Sparse | PostgreSQL `tsvector` full-text search (BM25-like) |
| Fusion | `QueryFusionRetriever` with `mode="relative_score"` |

RSF normalises each leg's scores to `[0, 1]` and averages them equally — there is no explicit beta/alpha weight and this is **not** Reciprocal Rank Fusion (RRF).

#### 2. Vector Index

HNSW via pgvector (`vector_cosine_ops`), configured in both `embed_pipeline` and `rag/retriever.py`:

| Parameter | Value |
|---|---|
| `hnsw_m` | 16 (max neighbours per node) |
| `hnsw_ef_construction` | 64 (build-time beam width) |
| `hnsw_ef_search` | 40 (query-time beam width) |
| Distance metric | Cosine (`vector_cosine_ops`) |

#### 3. Chunking Strategy

No text splitter is used. Each `topic_content` DB row is embedded as a single `TextNode`. One scanned page → one OCR `.md` file → one DB row → one vector. Chunk size is whatever fits on a textbook page.

#### 4. Query Rewriting + Intent Classification

Yes — implemented in `rag/query_rewriter.py`. Before retrieval, the RAG model rewrites the query and classifies its intent in a single LLM call.

**Rewritten query** is keyword-dense (filler words removed, textbook synonyms added) and is used for retrieval only — this improves recall on both the dense and sparse legs.

**Intent** controls which synthesis prompt template is selected and is also prepended to the original question as `[intent] original question` passed to the synthesiser — so the LLM gets the precise original question alongside an explicit behavioural signal.

| Intent | When | Synthesis behaviour |
|---|---|---|
| `definition` | asking for a definition, property, or formula | quote the context verbatim |
| `computation` | asking to solve a problem or find an unknown value | apply rules step-by-step, show working, state final answer |
| `explanation` | asking how/why something works | synthesise in own words from context |

Unknown intents fall back to `"explanation"` at both the rewriter and the template lookup.

#### 5. Reranking

None. After RSF fusion, top-k nodes go directly to the `CompactAndRefine` response synthesiser. `CompactAndRefine` is a response strategy (iterative refinement over chunks), not a reranker.

#### 6. LLM Parameters

Only the following are explicitly set (all others use provider defaults):

| Parameter | Value | Configured via |
|---|---|---|
| `context_window` | 4096 | `LLM_CONTEXT_WINDOW` env var |
| `request_timeout` | 360 s | `LLM_REQUEST_TIMEOUT` env var |
| `thinking` | false | `LLM_THINKING` env var |

Not set: temperature, top_k, top_p, repetition penalty, frequency penalty, presence penalty, logit bias, max_tokens. For the default Ollama `qwen3.5:9b` model, provider defaults apply (typically `temperature=0.8`, `top_k=40`, `top_p=0.9`).
