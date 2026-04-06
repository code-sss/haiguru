"""Central config loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_DIM: int = int(os.getenv("EMBED_DIM", "768"))
MODEL_PATH: str | None = os.getenv("MODEL_PATH")
