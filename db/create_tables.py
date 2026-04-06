"""Create all tables in the database.

Run once after `docker compose up -d`:
    uv run python -m db.create_tables
"""

from sqlalchemy import create_engine

from db.models import Base

DATABASE_URL = "postgresql://haiguru:haiguru_pass@localhost:5433/haiguru_db"

if __name__ == "__main__":
    engine = create_engine(DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)
    print("All tables created.")
