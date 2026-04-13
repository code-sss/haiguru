# LlamaIndex in the RAG Pipeline: Keep or Replace?

## What LlamaIndex Does Here

LlamaIndex is used in two places: `embed_pipeline/` and `rag/retriever.py`. In both cases it acts as a thin convenience wrapper — the actual performance-critical work happens in Postgres (pgvector, HNSW, tsvector) and in the embedding model.

| LlamaIndex component | What it actually does | Direct replacement |
|---|---|---|
| `PGVectorStore` | Generates SQL for `<=>` cosine and `tsvector` queries | Raw SQL with `pgvector` library |
| `VectorStoreIndex` + `insert_nodes` | Calls embed model, then `INSERT INTO topic_content_vectors` | Embed directly, then SQLAlchemy insert |
| `QueryFusionRetriever` (relative score) | ~20 lines of float math to merge two result lists | Implement fusion manually |
| `MetadataFilters` | Adds `WHERE` clauses to the SQL | Add `WHERE` clauses directly |
| `TextNode` | A dict with `id`, `text`, `metadata` | A dataclass or plain dict |

## Performance Impact of Removing LlamaIndex

**None.** The HNSW index, cosine similarity, and tsvector full-text search all live in Postgres. LlamaIndex does not influence retrieval quality at runtime — it only generates the SQL that invokes these Postgres features.

The embedding model (sentence-transformers / Ollama / OpenAI, configured via `llm_factory.py`) is equally unaffected — LlamaIndex simply calls it.

## Reasons to Remove LlamaIndex

- Heavy dependency tree — pulls in dozens of transitive packages.
- Abstraction leaks: HNSW kwargs, query modes, and filter syntax are already being passed as raw config through the LlamaIndex API.
- Harder to debug — SQL is generated indirectly and not visible without tracing.
- LlamaIndex version upgrades have historically broken `PGVectorStore` interfaces.
- Direct SQL gives full control over query plans, indexes, and result shaping.

## Reasons to Keep LlamaIndex

- The hybrid search wiring (dense + sparse + fusion) is already implemented and working.
- Replacing it is mechanical work (~150 lines of SQL + a simple fusion function) with no feature gain.

## What a Direct Replacement Looks Like

### Embedding (replaces `embed_pipeline/`)

```python
from pgvector.sqlalchemy import Vector
# 1. Call embedding model directly to get float list
# 2. INSERT INTO topic_content_vectors (id, text, embedding, metadata) VALUES (...)
```

### Retrieval (replaces `rag/retriever.py`)

```python
# Dense leg
SELECT id, text, metadata, 1 - (embedding <=> :query_vec) AS score
FROM topic_content_vectors
WHERE metadata->>'grade' = :grade   -- metadata filters
ORDER BY embedding <=> :query_vec
LIMIT :top_k;

# Sparse leg
SELECT id, text, metadata, ts_rank(to_tsvector('english', text), query) AS score
FROM topic_content_vectors, plainto_tsquery('english', :query_text) query
WHERE to_tsvector('english', text) @@ query
LIMIT :top_k;
```

### Fusion (replaces `QueryFusionRetriever`)

Relative score fusion: normalize each leg's scores to [0, 1], then average (or weight) them for results that appear in both legs. Union results for items appearing in only one leg.

## Recommendation

Keep LlamaIndex if the pipeline is stable and there is no immediate need to change it. Replace it if:

- The dependency weight becomes a problem (Docker image size, install time, conflicts).
- You need fine-grained control over SQL (custom ranking, query plan hints, batching).
- A LlamaIndex upgrade breaks the interface.

Replacing it is low-risk — all the hard work (pgvector, HNSW, tsvector) stays exactly as-is in Postgres.
