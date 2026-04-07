"""Factory function to create a reranker node post-processor from a model spec.

Model name conventions (same prefix style as llm_factory.py):
  <plain-name>                → local CrossEncoder via sentence-transformers
  cohere://<model-name>       → Cohere Rerank API (COHERE_API_KEY)
  jina://<model-name>         → Jina AI Rerank API (JINA_API_KEY)

Examples:
  cross-encoder/ms-marco-MiniLM-L-6-v2  (default, fully local)
  cohere://rerank-english-v3.0
  jina://jina-reranker-v2-base-en
"""

from __future__ import annotations

import os
from typing import Optional

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle


class _LocalCrossEncoderReranker(BaseNodePostprocessor):
    def __init__(self, model: str, top_n: int, model_path: str | None = None):
        super().__init__()
        from sentence_transformers import CrossEncoder
        self._encoder = CrossEncoder(model, **({"cache_folder": model_path} if model_path else {}))
        self._top_n = top_n

    @classmethod
    def class_name(cls) -> str:
        return "LocalCrossEncoderReranker"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes
        query = query_bundle.query_str
        pairs = [(query, n.node.get_content()) for n in nodes]
        scores = self._encoder.predict(pairs)
        reranked = sorted(zip(scores, nodes), key=lambda x: x[0], reverse=True)
        return [
            NodeWithScore(node=n.node, score=float(s))
            for s, n in reranked[: self._top_n]
        ]


class _CohereReranker(BaseNodePostprocessor):
    def __init__(self, model: str, top_n: int, api_key: str):
        super().__init__()
        self._model = model
        self._top_n = top_n
        self._api_key = api_key

    @classmethod
    def class_name(cls) -> str:
        return "CohereReranker"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes
        import httpx

        docs = [n.node.get_content() for n in nodes]
        resp = httpx.post(
            "https://api.cohere.com/v1/rerank",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "query": query_bundle.query_str,
                "documents": docs,
                "top_n": self._top_n,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        return [
            NodeWithScore(node=nodes[r["index"]].node, score=r["relevance_score"])
            for r in results
        ]


class _JinaReranker(BaseNodePostprocessor):
    def __init__(self, model: str, top_n: int, api_key: str):
        super().__init__()
        self._model = model
        self._top_n = top_n
        self._api_key = api_key

    @classmethod
    def class_name(cls) -> str:
        return "JinaReranker"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes
        import httpx

        docs = [n.node.get_content() for n in nodes]
        resp = httpx.post(
            "https://api.jina.ai/v1/rerank",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "query": query_bundle.query_str,
                "documents": docs,
                "top_n": self._top_n,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        return [
            NodeWithScore(node=nodes[r["index"]].node, score=r["relevance_score"])
            for r in results
        ]


def make_reranker(
    model_spec: str,
    *,
    top_n: int,
    model_path: str | None = None,
) -> BaseNodePostprocessor:
    """Return a reranker node post-processor for the given model spec.

    Args:
        model_spec:  Model identifier with optional provider prefix.
        top_n:       Number of nodes to keep after reranking.
        model_path:  Local cache directory for sentence-transformers models.
    """
    if "://" not in model_spec:
        return _LocalCrossEncoderReranker(
            model=model_spec,
            top_n=top_n,
            model_path=model_path,
        )

    provider, model_name = model_spec.split("://", 1)

    if provider == "cohere":
        api_key = os.environ.get("COHERE_API_KEY", "")
        if not api_key:
            raise ValueError("[reranker_factory] COHERE_API_KEY is not set.")
        return _CohereReranker(model=model_name, top_n=top_n, api_key=api_key)

    if provider == "jina":
        api_key = os.environ.get("JINA_API_KEY", "")
        if not api_key:
            raise ValueError("[reranker_factory] JINA_API_KEY is not set.")
        return _JinaReranker(model=model_name, top_n=top_n, api_key=api_key)

    raise ValueError(
        f"[reranker_factory] Unknown reranker provider: {provider!r}. "
        "Use cohere://, jina://, or a plain cross-encoder model name."
    )
