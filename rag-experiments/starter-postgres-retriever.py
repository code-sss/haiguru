import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from llama_index.core import SimpleDirectoryReader, StorageContext
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
import textwrap
import psycopg2
from sqlalchemy import make_url
import dotenv
from llama_index.core import Settings
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.query_engine import RetrieverQueryEngine

# Reload the variables in your '.env' file (override the existing variables)
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

documents = SimpleDirectoryReader("llama-index/data").load_data()
print("Document ID:", documents[0].doc_id)

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
    table_name="paul_graham_essay_hybrid_search",
    embed_dim=768,  # embedding dimension
    hybrid_search=True,
    text_search_config="english",
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

# storage_context = StorageContext.from_defaults(vector_store=hybrid_vector_store)
# hybrid_index = VectorStoreIndex.from_documents(
#     documents, storage_context=storage_context, embed_model=Settings.embed_model, show_progress=True
# )
hybrid_index = VectorStoreIndex.from_vector_store(vector_store=hybrid_vector_store)

# query_engine = hybrid_index.as_query_engine(
#         llm=Settings.llm,
#         vector_store_query_mode="hybrid",
#         sparse_top_k=5,
#         similarity_top_k=5,
#         hybrid_top_k=6
#     )

vector_retriever = hybrid_index.as_retriever(
    vector_store_query_mode="default",
    similarity_top_k=5,
)
text_retriever = hybrid_index.as_retriever(
    vector_store_query_mode="sparse",
    similarity_top_k=5,  # interchangeable with sparse_top_k in this context
)
retriever = QueryFusionRetriever(
    [vector_retriever, text_retriever],
    similarity_top_k=5,
    num_queries=1,  # set this to 1 to disable query generation
    mode="relative_score",
    use_async=False,
)

response_synthesizer = CompactAndRefine()
query_engine = RetrieverQueryEngine(
    retriever=retriever,
    response_synthesizer=response_synthesizer,
)

# response = query_engine.query("What did the author do in college?")
response = query_engine.query(
    "which person does Paul Graham think of with the word schtick, and why?"
)
print(textwrap.fill(str(response), width=100))