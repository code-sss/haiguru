"""CLI entry-point for the hybrid retriever + answer synthesis.

Retrieval  : dense HNSW + sparse tsvector, fused with relative-score ranking
Synthesis  : qwen3.5:9b via Ollama (CompactAndRefine)

Usage:
    uv run python -m rag "explain integers"
    uv run python -m rag "what is a prime number" --grade GRADE_7 --subject MATHEMATICS
    uv run python -m rag "integers" --grade GRADE_7 --grade GRADE_8   # OR across grades
    uv run python -m rag "addition rules" --topic-id <uuid>
    uv run python -m rag "fractions" --top-k 8 --retrieve-only
"""

import argparse
import os
import sys

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_index.core import Settings
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.vector_stores.types import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from config import EMBED_DIM, EMBED_MODEL, LLM_CONTEXT_WINDOW, RAG_MODEL, LLM_REQUEST_TIMEOUT, LLM_THINKING
from llm_factory import make_llm
from rag.retriever import build_retriever


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hybrid retriever + Ollama synthesis over haiguru content"
    )
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument("--top-k", type=int, default=5, help="Results per retriever leg (default: 5)")
    parser.add_argument("--grade", action="append", metavar="GRADE", help="Filter by grade (repeatable for OR, e.g. --grade GRADE_7 --grade GRADE_8)")
    parser.add_argument("--subject", action="append", metavar="SUBJECT", help="Filter by subject (repeatable for OR)")
    parser.add_argument("--course", action="append", metavar="COURSE", help="Filter by course (repeatable for OR)")
    parser.add_argument("--topic-id", help="Filter by topic UUID")
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="Print retrieved chunks only, skip LLM synthesis",
    )
    return parser.parse_args()


def _or_group(key: str, values: list[str]) -> MetadataFilters | MetadataFilter:
    """Return a single EQ filter for one value, or an OR-combined group for many."""
    if len(values) == 1:
        return MetadataFilter(key=key, value=values[0], operator=FilterOperator.EQ)
    return MetadataFilters(
        filters=[MetadataFilter(key=key, value=v, operator=FilterOperator.EQ) for v in values],
        condition=FilterCondition.OR,
    )


def _build_filters(args: argparse.Namespace) -> MetadataFilters | None:
    clauses = []
    if args.grade:
        clauses.append(_or_group("grade", args.grade))
    if args.subject:
        clauses.append(_or_group("subject", args.subject))
    if args.course:
        clauses.append(_or_group("course", args.course))
    if args.topic_id:
        clauses.append(MetadataFilter(key="topic_id", value=args.topic_id, operator=FilterOperator.EQ))
    return MetadataFilters(filters=clauses, condition=FilterCondition.AND) if clauses else None


def _print_nodes(nodes) -> None:
    if not nodes:
        print("No results found.")
        return
    for i, node in enumerate(nodes, 1):
        m = node.metadata
        score = f"{node.score:.4f}" if node.score is not None else "n/a"
        print(f"\n[{i}] score={score}")
        print(f"    topic  : {m.get('topic_title')} (page {m.get('page_order')})")
        print(f"    path   : {m.get('grade')} / {m.get('subject')} / {m.get('course')}")
        snippet = node.text[:300].replace("\n", " ")
        print(f"    text   : {snippet}...")


def main() -> None:
    args = _parse_args()
    filters = _build_filters(args)

    print(f"\nQuery        : {args.query!r}")
    print(f"Embed model  : {EMBED_MODEL} (dim={EMBED_DIM}, device=cpu)")
    print(f"RAG model    : {RAG_MODEL} (context_window={LLM_CONTEXT_WINDOW}, timeout={LLM_REQUEST_TIMEOUT}s, thinking={LLM_THINKING})")
    print(f"Top-k        : {args.top_k}")
    if filters:
        print(f"Filters      : {filters}")
    print("-" * 60)

    retriever = build_retriever(top_k=args.top_k, filters=filters)

    if args.retrieve_only:
        nodes = retriever.retrieve(args.query)
        _print_nodes(nodes)
        return

    # Full RAG: retrieve + synthesise
    llm = make_llm(RAG_MODEL, request_timeout=LLM_REQUEST_TIMEOUT, context_window=LLM_CONTEXT_WINDOW, thinking=LLM_THINKING)
    Settings.llm = llm

    query_engine = RetrieverQueryEngine(
        retriever=retriever,
        response_synthesizer=CompactAndRefine(llm=llm),
    )

    response = query_engine.query(args.query)

    print(f"\nAnswer ({RAG_MODEL}):\n")
    print(str(response))

    if response.source_nodes:
        print("\nSources:")
        _print_nodes(response.source_nodes)


if __name__ == "__main__":
    main()
