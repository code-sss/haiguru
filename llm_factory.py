"""Factory functions to create LlamaIndex LLM and embedding objects from a model spec.

Model name conventions (same as glm_ocr/client.py):
  <plain-name>                → Ollama (local, default) for LLM; HuggingFace (local) for embed
  openai://gpt-4o             → OpenAI (OPENAI_API_KEY)
  anthropic://claude-3-5-...  → Anthropic (ANTHROPIC_API_KEY)
  together://<model-path>     → TogetherAI OpenAI-compat (TOGETHER_API_KEY)
"""

from __future__ import annotations

import os

from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM


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

        return HuggingFaceEmbedding(
            model_name=model_spec,
            device=device,
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
