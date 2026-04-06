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
import asyncio
from llama_index.core.agent.workflow import AgentWorkflow

# Reload the variables in your '.env' file (override the existing variables)
dotenv.load_dotenv(".env", override=True)

# Load the pre-trained sentence transformer model using the method .encode
# model_name =  "BAAI/bge-base-en-v1.5" # 768 dimensions
# model_name = "Qwen/Qwen3-Embedding-8B" # 1024 dimensions
model_name = "BAAI/bge-m3" #1024 dimensions

# Settings control global defaults
Settings.embed_model = HuggingFaceEmbedding(model_name=model_name, cache_folder=os.environ['MODEL_PATH'])
Settings.llm = Ollama(
    model="llama3.2",
    #  model="qwen3:4b",
    request_timeout=360.0,
    # Manually set the context window to limit memory usage
    context_window=8192,
)
db_ip = os.environ.get("PG_DB_IP", "localhost")
db_port = os.environ.get("PG_DB_PORT", "5432")
db_name = os.environ.get("PG_DB_NAME", "vector_db")
user_name = os.environ.get("PG_USER")
password = os.environ.get("PG_PASSWORD")


connection_string = f"postgresql://{user_name}:{password}@{db_ip}:{db_port}"
conn = psycopg2.connect(connection_string)
conn.autocommit = True

url = make_url(connection_string)
hybrid_vector_store = PGVectorStore.from_params(
    database=db_name,
    host=url.host,
    password=url.password,
    port=url.port,
    user=url.username,
    table_name="ncert_hybrid_search",
    embed_dim=1024,  # embedding dimension
    hybrid_search=True,
    text_search_config="english",
    hnsw_kwargs={
        "hnsw_m": 16,
        "hnsw_ef_construction": 64,
        "hnsw_ef_search": 40,
        "hnsw_dist_method": "vector_cosine_ops",
    },
)

# documents = SimpleDirectoryReader("llama-index/data/ncert").load_data()
# print("Document ID:", documents[0].doc_id)
# storage_context = StorageContext.from_defaults(vector_store=hybrid_vector_store)
# hybrid_index = VectorStoreIndex.from_documents(
#     documents, storage_context=storage_context, embed_model=Settings.embed_model, show_progress=True
# )
hybrid_index = VectorStoreIndex.from_vector_store(vector_store=hybrid_vector_store)

# vector_retriever = hybrid_index.as_retriever(
#     vector_store_query_mode="default",
#     similarity_top_k=15,
# )
# text_retriever = hybrid_index.as_retriever(
#     vector_store_query_mode="sparse",
#     similarity_top_k=15,  # interchangeable with sparse_top_k in this context
# )
# retriever = QueryFusionRetriever(
#     [vector_retriever, text_retriever],
#     similarity_top_k=15,
#     # num_queries=1,  # set this to 1 to disable query generation
#     mode="relative_score",
#     use_async=False,
# )

# response_synthesizer = CompactAndRefine()
# query_engine = RetrieverQueryEngine(
#     retriever=retriever,
#     response_synthesizer=response_synthesizer,
# )
query_engine = hybrid_index.as_query_engine(
        llm=Settings.llm,
        vector_store_query_mode="hybrid",
        sparse_top_k=10,
        similarity_top_k=15,
        hybrid_top_k=10
    )

# response = query_engine.query("List the chapters in these PDFs in order with nice formatting")
# print(textwrap.fill(str(response), width=100))

def multiply(a: float, b: float) -> float:
    """Useful for multiplying two numbers."""
    return float(a) * float(b)


async def search_documents(query: str) -> str:
    """Useful for answering natural language questions about content from the PDFs."""
    print(f"\n{'='*80}")
    print(f"🔍 RETRIEVER CALLED")
    print(f"Query: {query}")
    print(f"{'='*80}")
    
    try:
        response = query_engine.query(query)  # Use sync query even in async function
        print(f"✓ Query completed successfully")
        
        # Check if source_nodes exist
        if hasattr(response, 'source_nodes') and response.source_nodes:
            print(f"\n📄 Retrieved {len(response.source_nodes)} source nodes:")
            for i, node in enumerate(response.source_nodes, 1):
                score = getattr(node, 'score', 'N/A')
                print(f"\n{'─'*80}")
                print(f"Source {i} | Similarity Score: {score}")
                print(f"{'─'*80}")
                print(f"{node.text[:300]}...")
        else:
            print(f"\n⚠️ No source nodes found in response")
        
        print(f"\n{'='*80}")
        print(f"✅ FINAL RESPONSE FROM QUERY ENGINE:")
        print(f"{response}")
        print(f"{'='*80}\n")
        return str(response)
    except Exception as e:
        print(f"❌ Error in search_documents: {e}")
        import traceback
        traceback.print_exc()
        raise

# Create an enhanced workflow with both tools
agent = AgentWorkflow.from_tools_or_functions(
    [multiply, search_documents],
    llm=Settings.llm,
    system_prompt="""You are a helpful assistant that can search through documents to answer questions.
    You first understand the question and rewrite it if necessary to improve clarity.""",
)

# Now we can ask questions about the documents or do calculations
async def main():
    response = await agent.run(
        "Table of Contents, chapters with page numbers and brief chapter summaries. nice formatting"
    )
    print(response)

# # Now we can ask questions about the documents or do calculations
# async def explain_me():
#     response = await agent.run(
#         "How to convert absolute temperature to celsius?"
#     )
#     print(response)

# Run the agent
if __name__ == "__main__":
    asyncio.run(main())