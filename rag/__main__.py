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
from llama_index.core.prompts import PromptTemplate
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.vector_stores.types import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from config import EMBED_DIM, EMBED_MODEL, LLM_CONTEXT_WINDOW, RAG_MODEL, LLM_REQUEST_TIMEOUT, LLM_THINKING, MODEL_PATH, RERANK_MODEL
from llm_factory import make_llm
from reranker_factory import make_reranker
from rag.retriever import build_retriever
from rag.query_rewriter import rewrite as rewrite_query, RewriteResult


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
    print(f"Rerank model : {RERANK_MODEL or '(disabled)'}")
    print(f"Top-k        : {args.top_k}")
    if filters:
        print(f"Filters      : {filters}")
    print("-" * 60)

    # LLM is needed for query rewriting regardless of --retrieve-only
    llm = make_llm(RAG_MODEL, request_timeout=LLM_REQUEST_TIMEOUT, context_window=LLM_CONTEXT_WINDOW, thinking=LLM_THINKING)
    Settings.llm = llm

    # --- Query rewriting + intent classification + safety check ---
    result: RewriteResult = rewrite_query(args.query, llm)
    print(f"Rewritten query : {result.rewritten_query!r}")
    print(f"Intent          : {result.intent}")
    print(f"Safe            : {result.safe}")
    print("-" * 60)

    if not result.safe:
        print(f"\n{result.reject_reason}")
        return

    fetch_k = args.top_k * 3 if RERANK_MODEL else args.top_k
    retriever = build_retriever(top_k=fetch_k, filters=filters)

    if args.retrieve_only:
        nodes = retriever.retrieve(result.rewritten_query)
        if RERANK_MODEL:
            reranker = make_reranker(RERANK_MODEL, top_n=args.top_k, model_path=MODEL_PATH)
            from llama_index.core.schema import QueryBundle
            nodes = reranker.postprocess_nodes(nodes, query_bundle=QueryBundle(args.query))
        _print_nodes(nodes)
        return

    # --- Intent-specific prompt templates ---
    _QA_TEMPLATES = {
        "definition": PromptTemplate(
            "You are an educational assistant. The student is asking for a definition or factual statement.\n"
            "Find the relevant definition or property in the context and quote it verbatim.\n"
            "If the context does not contain the answer, say 'I don't know based on the available content'.\n\n"
            "Context:\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n\n"
            "Question: {query_str}\n"
            "Answer: "
        ),
        "computation": PromptTemplate(
            "You are an educational assistant. The student has a specific problem to solve.\n"
            "Use the rules and methods from the context to solve it step-by-step. Show all working clearly.\n"
            "State the final answer explicitly at the end.\n"
            "Ground every step in the context — do not introduce methods not present in it.\n"
            "If the context does not contain enough information to solve the problem, say 'I don't know based on the available content'.\n\n"
            "Context:\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n\n"
            "Question: {query_str}\n"
            "Answer: "
        ),
        "explanation": PromptTemplate(
            "You are an educational assistant. The student wants a concept explained.\n"
            "Synthesise a clear explanation using ONLY the provided context. Use your own words but stay faithful to the source.\n"
            "Include examples from the context where helpful.\n"
            "If the context does not contain the answer, say 'I don't know based on the available content'.\n\n"
            "Context:\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n\n"
            "Question: {query_str}\n"
            "Answer: "
        ),
    }

    _REFINE_TEMPLATES = {
        "definition": PromptTemplate(
            "You are an educational assistant. The original question is: {query_str}\n"
            "We have an existing answer: {existing_answer}\n"
            "If the additional context contains a more precise or complete definition, update the answer. Otherwise return it unchanged.\n\n"
            "Additional context:\n"
            "---------------------\n"
            "{context_msg}\n"
            "---------------------\n\n"
            "Refined answer: "
        ),
        "computation": PromptTemplate(
            "You are an educational assistant. The original question is: {query_str}\n"
            "We have an existing answer: {existing_answer}\n"
            "If the additional context provides more relevant rules or steps that improve the solution, refine the working and restate the final answer.\n"
            "If the new context is not useful, return the existing answer unchanged.\n\n"
            "Additional context:\n"
            "---------------------\n"
            "{context_msg}\n"
            "---------------------\n\n"
            "Refined answer: "
        ),
        "explanation": PromptTemplate(
            "You are an educational assistant. The original question is: {query_str}\n"
            "We have an existing answer: {existing_answer}\n"
            "Refine the explanation using the additional context if it adds useful detail or examples.\n"
            "If the new context is not useful, return the existing answer unchanged.\n\n"
            "Additional context:\n"
            "---------------------\n"
            "{context_msg}\n"
            "---------------------\n\n"
            "Refined answer: "
        ),
    }

    qa_template = _QA_TEMPLATES.get(result.intent, _QA_TEMPLATES["explanation"])
    refine_template = _REFINE_TEMPLATES.get(result.intent, _REFINE_TEMPLATES["explanation"])

    # Retrieve with the rewritten query (keyword-dense, better recall).
    # Rerank against the original query (natural language, better precision).
    # Synthesise with the original query prefixed by intent so the LLM gets
    # both the precise question and an explicit signal of what to do.
    nodes = retriever.retrieve(result.rewritten_query)
    if RERANK_MODEL:
        reranker = make_reranker(RERANK_MODEL, top_n=args.top_k, model_path=MODEL_PATH)
        from llama_index.core.schema import QueryBundle
        nodes = reranker.postprocess_nodes(nodes, query_bundle=QueryBundle(args.query))
    synthesis_query = f"[{result.intent}] {args.query}"

    synthesizer = CompactAndRefine(
        llm=llm,
        text_qa_template=qa_template,
        refine_template=refine_template,
    )
    response = synthesizer.synthesize(synthesis_query, nodes=nodes)

    print(f"\nAnswer ({RAG_MODEL}):\n")
    print(str(response))

    if response.source_nodes:
        print("\nSources:")
        _print_nodes(response.source_nodes)


if __name__ == "__main__":
    main()
