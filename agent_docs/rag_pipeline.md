# RAG Pipeline Internals

Covers the four-stage RAG pipeline in `rag/` — query rewriting, retrieval, reranking, and synthesis.

## Stages

1. **Query rewriting + intent + safety** (`rag/query_rewriter.py`)
   Returns a `RewriteResult`:
   - `rewritten_query`: keyword-dense version used for retrieval
   - `intent`: `"definition"` | `"computation"` | `"explanation"` — selects synthesis template
   - `safe`: `False` rejects the query (profanity, prompt injection, harmful content); off-topic benign queries pass through
   - `reject_reason`: user-facing message when `safe=False`
   - Parse errors fail safe — query is rejected, not passed through

2. **Hybrid retrieval** (`rag/retriever.py`)
   Fused dense (HNSW cosine) + sparse (tsvector) search on the rewritten query.
   Fetches `top_k × 3` candidates when reranking is active.

3. **Reranking** (`reranker_factory.py`)
   Cross-encoder reranks candidates against the **original** query (not rewritten).
   Controlled by `RERANK_MODEL` in `.env` (empty string = disabled).

4. **Synthesis** (`rag/__main__.py`)
   `CompactAndRefine` with intent-specific templates. Synthesiser receives
   `[intent] original_query` — NOT the rewritten query — to preserve semantic precision.

## Adding a New Intent

1. Add an example to `_REWRITE_PROMPT` in `rag/query_rewriter.py`
2. Add entries to `_QA_TEMPLATES` and `_REFINE_TEMPLATES` in `rag/__main__.py`

Unknown intents fall back to `"explanation"`.

## Gotchas

- The reranker uses the **original** query, not the rewritten one — don't change this; it's intentional.
- Parse errors in the rewriter reject the query rather than silently falling through.
- When adding an intent, both the rewriter examples AND the synthesis templates must be updated or synthesis silently falls back to `"explanation"`.
