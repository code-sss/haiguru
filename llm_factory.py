"""Factory functions to create LlamaIndex LLM and embedding objects from a model spec.

Model name conventions (same as glm_ocr/client.py):
  <plain-name>                → Ollama (local, default) for LLM; HuggingFace (local) for embed
  openai://gpt-4o             → OpenAI (OPENAI_API_KEY)
  anthropic://claude-3-5-...  → Anthropic (ANTHROPIC_API_KEY)
  together://<model-path>     → TogetherAI OpenAI-compat (TOGETHER_API_KEY)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM


def _is_local_model_dir(path: Path) -> bool:
    return (path / "config.json").exists() or (path / "modules.json").exists()


def _resolve_local_hf_model_path(model_spec: str, model_path: str | None) -> str | None:
    """Resolve a Hugging Face cache root to a concrete local model directory.

    MODEL_PATH may point either to a model directory directly or to a Hugging Face
    cache root containing models--<org>--<name>/snapshots/<revision>.
    """
    if not model_path:
        return None

    cache_root = Path(model_path).expanduser()
    direct_candidates = [cache_root, cache_root / model_spec]
    for candidate in direct_candidates:
        if candidate.is_dir() and _is_local_model_dir(candidate):
            return str(candidate)

    repo_cache_dir = cache_root / f"models--{model_spec.replace('/', '--')}"
    snapshots_dir = repo_cache_dir / "snapshots"
    if not snapshots_dir.is_dir():
        return None

    ref_file = repo_cache_dir / "refs" / "main"
    if ref_file.is_file():
        snapshot_name = ref_file.read_text(encoding="utf-8").strip()
        candidate = snapshots_dir / snapshot_name
        if candidate.is_dir() and _is_local_model_dir(candidate):
            return str(candidate)

    for candidate in sorted(snapshots_dir.iterdir(), reverse=True):
        if candidate.is_dir() and _is_local_model_dir(candidate):
            return str(candidate)

    return None


def make_llm(
    model_spec: str,
    *,
    request_timeout: float = 360.0,
    context_window: int = 4096,
    thinking: bool = False,
) -> LLM:
    """Return a LlamaIndex LLM for the given model spec.

    Defaults to Ollama for plain model names.
    """
    if "://" not in model_spec:
        from llama_index.llms.ollama import Ollama

        return Ollama(
            model=model_spec,
            request_timeout=request_timeout,
            context_window=context_window,
            thinking=thinking,
        )

    provider, model_name = model_spec.split("://", 1)

    if provider == "openai":
        from llama_index.llms.openai import OpenAI

        return OpenAI(model=model_name, api_key=os.environ.get("OPENAI_API_KEY"))

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic

        return Anthropic(model=model_name, api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if provider == "together":
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=model_name,
            api_base="https://api.together.xyz/v1",
            api_key=os.environ.get("TOGETHER_API_KEY", ""),
            is_chat_model=True,
            context_window=context_window,
        )

    raise ValueError(
        f"[llm_factory] Unknown LLM provider: {provider!r}. "
        "Use openai://, anthropic://, together://, or a plain Ollama model name."
    )


def make_embed_model(
    model_spec: str,
    *,
    device: str = "cpu",
    model_path: str | None = None,
) -> BaseEmbedding:
    """Return a LlamaIndex embedding model for the given model spec.

    Defaults to HuggingFaceEmbedding for plain model names.
    """
    if "://" not in model_spec:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        local_model_path = _resolve_local_hf_model_path(model_spec, model_path)
        model_name = local_model_path or model_spec
        model_kwargs: dict[str, Any] = {"local_files_only": True} if local_model_path else {}

        return HuggingFaceEmbedding(
            model_name=model_name,
            device=device,
            **model_kwargs,
            **({"cache_folder": model_path} if model_path else {}),
        )

    provider, model_name = model_spec.split("://", 1)

    if provider == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model=model_name,
            api_key=os.environ.get("OPENAI_API_KEY"),
            embed_batch_size=64,
        )

    if provider == "together":
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model=model_name,
            api_base="https://api.together.xyz/v1",
            api_key=os.environ.get("TOGETHER_API_KEY", ""),
            embed_batch_size=64,
        )

    raise ValueError(
        f"[llm_factory] Unknown embedding provider: {provider!r}. "
        "Use openai://, together://, or a plain HuggingFace model name."
    )
