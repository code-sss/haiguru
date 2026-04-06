"""Shared pytest configuration and fixtures.

Sets DATABASE_URL before any test module is imported so that config.py
(which does os.environ["DATABASE_URL"] at import time) does not raise KeyError
during test collection.  Unit tests never actually connect to the DB.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://haiguru:haiguru_pass@localhost:5433/haiguru_db")
