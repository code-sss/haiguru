"""Hybrid (dense + sparse) retriever over haiguru topic_content_vectors.

Public API:
    build_retriever(top_k, filters) -> QueryFusionRetriever

The retriever fuses:
  - Dense leg  : cosine HNSW vector similarity
  - Sparse leg : PostgreSQL tsvector full-text search
  - Fusion     : relative-score re-ranking (no LLM query generation)

The embedding model is initialised once on first call and cached in
llama_index Settings so subsequent calls are cheap.
"""

from __future__ import annotations

import os

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HUGGINGFACE_HUB_OFFLINE", "1")

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.vector_stores.types import MetadataFilters
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import make_url

from config import DATABASE_URL, EMBED_DEVICE, EMBED_DIM, EMBED_MODEL, MODEL_PATH
from llm_factory import make_embed_model

TABLE_NAME = "topic_content_vectors"

_embed_model_initialised = False


def _ensure_embed_model() -> None:
    global _embed_model_initialised
    if not _embed_model_initialised:
        Settings.embed_model = make_embed_model(EMBED_MODEL, device=EMBED_DEVICE, model_path=MODEL_PATH)
        _embed_model_initialised = True


def _make_vector_store() -> PGVectorStore:
    url = make_url(DATABASE_URL)
    return PGVectorStore.from_params(
        database=url.database,
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        table_name=TABLE_NAME,
        embed_dim=EMBED_DIM,
        hybrid_search=True,
        text_search_config="english",
        hnsw_kwargs={
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
            "hnsw_ef_search": 40,
            "hnsw_dist_method": "vector_cosine_ops",
        },
    )


def build_retriever(
    top_k: int = 5,
    filters: MetadataFilters | None = None,
) -> QueryFusionRetriever:
    """Return a fused dense+sparse retriever over topic_content_vectors.

    Args:
        top_k:   Number of results each leg returns; fusion re-ranks to top_k.
        filters: Optional MetadataFilters to restrict by grade/subject/course/topic.
    """
    _ensure_embed_model()

    index = VectorStoreIndex.from_vector_store(vector_store=_make_vector_store())

    vector_retriever = index.as_retriever(
        vector_store_query_mode="default",
        similarity_top_k=top_k,
        filters=filters,
    )
    text_retriever = index.as_retriever(
        vector_store_query_mode="sparse",
        similarity_top_k=top_k,
        filters=filters,
    )

    return QueryFusionRetriever(
        [vector_retriever, text_retriever],
        similarity_top_k=top_k,
        num_queries=1,        # disable LLM query expansion — use query verbatim
        mode="relative_score",
        use_async=False,
    )
