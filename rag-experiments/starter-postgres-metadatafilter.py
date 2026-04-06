import csv
from llama_index.core.schema import TextNode
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from datetime import datetime
import re
from llama_index.vector_stores.postgres import PGVectorStore
import psycopg2
from sqlalchemy import make_url
import dotenv
from llama_index.core import VectorStoreIndex
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"


dotenv.load_dotenv(".env", override=True)
dotenv.load_dotenv(".env", override=True)

# Load the pre-trained sentence transformer model using the method .encode
model_name =  "BAAI/bge-base-en-v1.5"

# Settings control global defaults
Settings.embed_model = HuggingFaceEmbedding(model_name=model_name, cache_folder=os.environ['MODEL_PATH'])
Settings.llm = Ollama(
    model="llama3.2",
    request_timeout=360.0,
    # Manually set the context window to limit memory usage
    # context_window=8000,
)


with open("llama-index/data/git_commits/commit_history.csv", "r") as f:
    commits = list(csv.DictReader(f))

nodes = []
dates = set()
authors = set()
for commit in commits[:100]:
    author_email = commit["author"].split("<")[1][:-1]
    commit_date = datetime.strptime(
        commit["date"], "%a %b %d %H:%M:%S %Y %z"
    ).strftime("%Y-%m-%d")
    commit_text = commit["change summary"]
    if commit["change details"]:
        commit_text += "\n\n" + commit["change details"]
    fixes = re.findall(r"#(\d+)", commit_text, re.IGNORECASE)
    nodes.append(
        TextNode(
            text=commit_text,
            metadata={
                "commit_date": commit_date,
                "author": author_email,
                "fixes": fixes,
            },
        )
    )
    dates.add(commit_date)
    authors.add(author_email)

db_ip = os.environ.get("PG_DB_IP", "localhost")
db_port = os.environ.get("PG_DB_PORT", "5432")
db_name = os.environ.get("PG_DB_NAME", "vector_db")
user_name = os.environ.get("PG_USER")
password = os.environ.get("PG_PASSWORD")


connection_string = f"postgresql://{user_name}:{password}@{db_ip}:{db_port}"
db_name = "vector_db"
conn = psycopg2.connect(connection_string)
conn.autocommit = True

url = make_url(connection_string)
hybrid_vector_store = PGVectorStore.from_params(
    database=db_name,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="metadata_filter_demo3",
    embed_dim=768,  # openai embedding dimension
    hybrid_search=True,
    text_search_config="english",
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

hybrid_index = VectorStoreIndex.from_vector_store(vector_store=hybrid_vector_store)
# hybrid_index.insert_nodes(nodes)

# print(hybrid_index.as_query_engine(llm=Settings.llm,).query("How did Lakshmi fix the segfault?"))

from llama_index.core.vector_stores.types import (
    MetadataFilter,
    MetadataFilters,
)

filters = MetadataFilters(
    filters=[
        MetadataFilter(key="author", value="mats@timescale.com"),
        MetadataFilter(key="author", value="sven@timescale.com"),
    ],
    condition="or",
)

retriever = hybrid_index.as_retriever(
    similarity_top_k=10,
    filters=filters,
)

retrieved_nodes = retriever.retrieve("What is this software project about?")

for node in retrieved_nodes:
    print(node.node.metadata)

print("----- Date Range Filter -----")


filters = MetadataFilters(
    filters=[
        MetadataFilter(key="commit_date", value="2023-08-15", operator=">="),
        MetadataFilter(key="commit_date", value="2023-08-25", operator="<="),
    ],
    condition="and",
)

retriever = hybrid_index.as_retriever(
    vector_store_query_mode="hybrid",
    similarity_top_k=10,
    sparse_top_k=10,
    filters=filters,
)

retrieved_nodes = retriever.retrieve("What is this software project about?")

for node in retrieved_nodes:
    print(node.node.metadata)