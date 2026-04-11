# LLM Providers & Environment Variables

Covers provider prefix routing and all configurable environment variables (`config.py`).

## Provider Prefix Routing

Three pipelines (ETL exercise parsing, RAG synthesis, embedding) share the same prefix convention
via `llm_factory.py` and `glm_ocr/client.py`:

| Prefix | Provider | Required env var |
|---|---|---|
| *(none)* | Ollama (local, default) | — |
| `openai://` | OpenAI | `OPENAI_API_KEY` |
| `anthropic://` | Anthropic | `ANTHROPIC_API_KEY` |
| `together://` | TogetherAI (OpenAI-compat) | `TOGETHER_API_KEY` |

The **reranker** uses separate routing in `reranker_factory.py`:

| Prefix | Provider | Required env var |
|---|---|---|
| *(none)* | Local cross-encoder (`sentence-transformers`, cached in `MODEL_PATH`) | — |
| `cohere://` | Cohere Rerank API | `COHERE_API_KEY` |
| `jina://` | Jina AI Rerank API | `JINA_API_KEY` |

## Environment Variables

| Variable | Used by | Default |
|---|---|---|
| `TRANSFORM_MODEL` | Exercise parsing LLM | `qwen3.5:9b` |
| `RAG_MODEL` | RAG synthesis LLM | `qwen3.5:9b` |
| `EMBED_MODEL` | Embedding model | `BAAI/bge-m3` (HuggingFace local) |
| `EMBED_DIM` | Embedding dimension | `1024` (bge-m3) |
| `RERANK_MODEL` | Reranker (empty = disabled) | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| `OPENAI_API_KEY` | OpenAI | — |
| `ANTHROPIC_API_KEY` | Anthropic | — |
| `TOGETHER_API_KEY` | TogetherAI | — |
| `COHERE_API_KEY` | Cohere reranker | — |
| `JINA_API_KEY` | Jina reranker | — |

## Examples

```bash
# Use GPT-4o for exercise parsing
uv run python -m etl_pipeline --topic-path "..." --type exercises --transform-model "openai://gpt-4o"

# Use Claude for RAG synthesis (.env)
RAG_MODEL=anthropic://claude-opus-4-5

# Use OpenAI embeddings (also update EMBED_DIM)
EMBED_MODEL=openai://text-embedding-3-large
EMBED_DIM=3072

# Use Cohere reranker
RERANK_MODEL=cohere://rerank-english-v3.0

# Disable reranking
RERANK_MODEL=
```

## Gotchas

- When switching embedding models, `EMBED_DIM` must match the model's output dimension or pgvector inserts will fail.
- `TRANSFORM_MODEL` can be set in `.env` or overridden per-run with `--transform-model`.
- Routing logic lives in: `llm_factory.py` (RAG/embed), `reranker_factory.py` (reranker), `glm_ocr/client.py` (OCR exercise parsing).
