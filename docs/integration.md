# Haiguru — Integration Guide for Microservices

Haiguru is a backend data and AI pipeline system for educational content and exams.
It is **not a REST API service** — integration happens through:

- **Direct PostgreSQL access** (shared DB)
- **Python module imports** (when co-located or as a package)
- **CLI invocation** (`uv run python -m [pipeline]`)

---

## Integration Model

```
Other service
    │
    ├── PostgreSQL (port 5433) ──────── read/write tables directly
    ├── Python imports ──────────────── use rag, db.ops, llm_factory
    └── CLI shell-out ───────────────── uv run python -m rag / etl_pipeline / ...
```

No message queues or webhooks. All operations are synchronous.

---

## Pipelines

| Pipeline | Module | Input | Output |
|---|---|---|---|
| **ETL** | `etl_pipeline` | Topic folder (images + prompts) | Upserts topics, questions, exam templates to DB |
| **Embed** | `embed_pipeline` | `topic_contents` rows in DB | HNSW vectors in `topic_content_vectors` |
| **RAG** | `rag` | Natural-language query string | Ranked text chunks + synthesised answer |
| **Eval** | `eval_pipeline` | `ExamSession` UUID | Grades written to `exam_session_questions` + `exam_sessions.score` |

---

## Data Model

Schema is in `db/models.py`, managed by Alembic. Full detail: [`agent_docs/data_model.md`](../agent_docs/data_model.md).

### Hierarchy

```
categories
  └── course_path_nodes          node_type: grade → subject → course
        └── topics
              ├── topic_contents   (text pages; embedded into pgvector)
              └── questions        (exercises; single_choice / essay / fill_in_the_blank / …)
                    └── paragraph_questions  (grouped under a passage)
```

### Exams

```
exam_templates  (linked to course_path_node)
  └── exam_template_questions    (ordered blueprint: question_id + points)

exam_sessions   (one user attempt at one exam_template)
  └── exam_session_questions     (user_answer, earned_points, is_correct)
```

### Key column notes

| Table | Gotcha |
|---|---|
| All tables | PKs are UUID |
| `questions.correct_answers` | Stores **resolved option text**, not letters like "(b)" |
| `questions.options` | JSONB array of plain strings |
| `paragraph_questions.question_ids` | Ordered UUID array — insertion order matters |
| `exam_sessions.user_id` | UUID, not yet FK-enforced — treat as advisory |
| `exam_sessions.status` | `pending` → `ongoing` → `completed` / `failed` |

---

## Python API

### RAG retrieval

```python
from rag.retriever import build_retriever

retriever = build_retriever(top_k=5)          # returns QueryFusionRetriever
nodes = retriever.retrieve("explain integers") # list of NodeWithScore

# With metadata filters
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
filters = MetadataFilters(filters=[
    ExactMatchFilter(key="grade", value="GRADE_7"),
    ExactMatchFilter(key="subject", value="MATHEMATICS"),
])
retriever = build_retriever(top_k=5, filters=filters)
```

### Query rewriting (intent + safety)

```python
from rag.query_rewriter import rewrite

result = rewrite("what is a prime number")
# result.rewritten_query  — keyword-dense version used for retrieval
# result.intent           — "definition" | "computation" | "explanation"
# result.safe             — False if query should be rejected
# result.reject_reason    — friendly message when safe=False
```

### LLM and embedding factories

```python
from llm_factory import make_llm, make_embed_model
from reranker_factory import make_reranker

llm = make_llm("openai://gpt-4o")
embed = make_embed_model("openai://text-embedding-3-large")
reranker = make_reranker("cohere://rerank-english-v3.0")
```

Provider prefix convention: no prefix = Ollama local, `openai://`, `anthropic://`, `together://`, `cohere://`, `jina://`.

### DB access

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db.models import Topic, TopicContent, Question, ExamSession, ExamTemplate
import os

engine = create_engine(os.environ["DATABASE_URL"])

with Session(engine) as session:
    topics = session.query(Topic).all()
    sessions = session.query(ExamSession).filter_by(user_id=user_id).all()
```

### DB helpers (upsert utilities)

```python
from db.ops import (
    get_or_create_category,
    get_or_create_topic,
    get_or_create_question,
)
```

---

## Connection Details

```
PostgreSQL  localhost:5433
Database    haiguru_db
User        haiguru
Password    haiguru_pass

DATABASE_URL=postgresql://haiguru:haiguru_pass@localhost:5433/haiguru_db
```

pgvector (`vector` extension) is enabled at DB init. The `topic_content_vectors` table is managed by LlamaIndex, not Alembic — do not run migrations against it.

---

## Environment Variables (consumer checklist)

```ini
# Required
DATABASE_URL=postgresql://haiguru:haiguru_pass@localhost:5433/haiguru_db

# Embedding (must match the model used when embed_pipeline was run)
EMBED_MODEL=BAAI/bge-m3          # default; or openai://text-embedding-3-large
EMBED_DIM=1024                   # must match model output dim (3072 for text-embedding-3-large)
MODEL_PATH=./models              # local cache dir for HuggingFace models

# LLM for RAG synthesis / exercise parsing / eval grading
RAG_MODEL=qwen3.5:9b             # default Ollama; or openai://gpt-4o, anthropic://claude-*
TRANSFORM_MODEL=qwen3.5:9b
EVAL_MODEL=qwen3.5:9b

# Reranker (optional)
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2   # default local; or cohere://, jina://, "" to disable

# API keys — only required for the providers you use
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
TOGETHER_API_KEY=...
COHERE_API_KEY=...
JINA_API_KEY=...
```

Full provider reference: [`agent_docs/llm_providers.md`](../agent_docs/llm_providers.md).

---

## Observability

All pipelines emit OpenInference traces via OpenTelemetry to Arize Phoenix:

```
http://localhost:6006
```

Instrumented automatically via `LlamaIndexInstrumentor`. Plug your own OTLP collector into the same endpoint if needed.

---

## What Haiguru Does Not Provide

- No HTTP API (no FastAPI/Flask routes)
- No authentication or authorisation
- No message queue consumers or producers
- No webhooks or callbacks

These are expected to be provided by the calling service.
