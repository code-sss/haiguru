"""Central config loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM: int = int(os.getenv("EMBED_DIM", "1024"))
MODEL_PATH: str | None = os.getenv("MODEL_PATH")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.5:9b")
LLM_CONTEXT_WINDOW: int = int(os.getenv("LLM_CONTEXT_WINDOW", "4096"))
LLM_REQUEST_TIMEOUT: float = float(os.getenv("LLM_REQUEST_TIMEOUT", "360"))
LLM_THINKING: bool = os.getenv("LLM_THINKING", "false").lower() in ("1", "true", "yes")
