"""Central config loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv(override=True)


def _resolve_device(requested: str) -> str:
    """Resolve 'auto' to the best available device (cuda > mps > cpu)."""
    if requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


DATABASE_URL: str = os.environ["DATABASE_URL"]
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM: int = int(os.getenv("EMBED_DIM", "1024"))
EMBED_DEVICE: str = _resolve_device(os.getenv("EMBED_DEVICE", "auto"))
MODEL_PATH: str | None = os.getenv("MODEL_PATH")
RAG_MODEL: str = os.getenv("RAG_MODEL", "qwen3.5:9b")
TRANSFORM_MODEL: str = os.getenv("TRANSFORM_MODEL", "qwen3.5:9b")
LLM_CONTEXT_WINDOW: int = int(os.getenv("LLM_CONTEXT_WINDOW", "4096"))
LLM_REQUEST_TIMEOUT: float = float(os.getenv("LLM_REQUEST_TIMEOUT", "360"))
LLM_THINKING: bool = os.getenv("LLM_THINKING", "false").lower() in ("1", "true", "yes")

RERANK_MODEL: str = os.getenv("RERANK_MODEL", "")  # empty = disabled

# API keys for external LLM providers (optional — only needed when using that provider)
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
TOGETHER_API_KEY: str | None = os.getenv("TOGETHER_API_KEY")
COHERE_API_KEY: str | None = os.getenv("COHERE_API_KEY")
JINA_API_KEY: str | None = os.getenv("JINA_API_KEY")
