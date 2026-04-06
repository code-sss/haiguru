"""Embed topic_contents into PGVectorStore using LlamaIndex.

Usage:
    uv run python -m embed_pipeline
    uv run python -m embed_pipeline --topic-id <uuid>   # single topic
"""

import os
import argparse
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import make_url

from config import DATABASE_URL, EMBED_MODEL, EMBED_DIM, MODEL_PATH

TABLE_NAME = "topic_content_vectors"

# SQL that walks the hierarchy up from topic_contents
CONTENT_QUERY = text("""
    SELECT
        tc.id            AS content_id,
        tc.topic_id,
        tc.title         AS content_title,
        tc.text,
        tc.order,
        t.title          AS topic_title,
        course.name      AS course_name,
        subject.name     AS subject_name,
        grade.name       AS grade_name,
        cat.name         AS category_name
    FROM topic_contents tc
    JOIN topics t         ON t.id = tc.topic_id
    JOIN course_path_nodes course  ON course.id  = t.course_path_node_id
    JOIN course_path_nodes subject ON subject.id = course.parent_id
    JOIN course_path_nodes grade   ON grade.id   = subject.parent_id
    JOIN categories cat            ON cat.id     = grade.category_id
    WHERE tc.content_type = 'text'
      AND tc.text IS NOT NULL
      AND tc.text != ''
      AND (:topic_id IS NULL OR tc.topic_id = CAST(:topic_id AS uuid))
    ORDER BY tc.topic_id, tc.order
""")


def build_nodes(rows) -> list[TextNode]:
    nodes = []
    for row in rows:
        node = TextNode(
            id_=str(row.content_id),
            text=row.text,
            metadata={
                "topic_content_id": str(row.content_id),
                "topic_id": str(row.topic_id),
                "topic_title": row.topic_title,
                "course": row.course_name,
                "subject": row.subject_name,
                "grade": row.grade_name,
                "category": row.category_name,
                "page_order": row.order,
            },
        )
        nodes.append(node)
    return nodes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic-id", default=None, help="Embed only this topic (UUID)")
    args = parser.parse_args()

    # Configure embedding model (no LLM needed for indexing)
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBED_MODEL,
        **({"cache_folder": MODEL_PATH} if MODEL_PATH else {}),
    )
    Settings.llm = None

    # Load rows from DB
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        rows = session.execute(CONTENT_QUERY, {"topic_id": args.topic_id}).fetchall()

    if not rows:
        print("No topic_content rows found — nothing to embed.")
        return

    print(f"Building nodes for {len(rows)} topic_content rows...")
    nodes = build_nodes(rows)

    # Connect vector store (same DB, separate table managed by pgvector)
    url = make_url(DATABASE_URL)
    vector_store = PGVectorStore.from_params(
        database=url.database,
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        table_name=TABLE_NAME,
        embed_dim=EMBED_DIM,
        hnsw_kwargs={
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
            "hnsw_ef_search": 40,
            "hnsw_dist_method": "vector_cosine_ops",
        },
    )

    index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
    print(f"Inserting {len(nodes)} nodes into '{TABLE_NAME}'...")
    index.insert_nodes(nodes)
    print("Done.")


if __name__ == "__main__":
    main()
