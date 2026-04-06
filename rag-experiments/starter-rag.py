from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import asyncio
import os
import dotenv

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
    context_window=8000,
)

# Create a RAG tool using LlamaIndex
documents = SimpleDirectoryReader("llama-index/data").load_data()
index = VectorStoreIndex.from_documents(
    documents,
    # we can optionally override the embed_model here
    embed_model=Settings.embed_model,
)
query_engine = index.as_query_engine(
    # we can optionally override the llm here
    llm=Settings.llm,
)

def multiply(a: float, b: float) -> float:
    """Useful for multiplying two numbers."""
    return float(a) * float(b)


async def search_documents(query: str) -> str:
    """Useful for answering natural language questions about an personal essay written by Paul Graham."""
    response = await query_engine.aquery(query)
    print(f"Search Documents Response: {response}")
    return str(response)

# Create an enhanced workflow with both tools
agent = AgentWorkflow.from_tools_or_functions(
    [multiply, search_documents],
    llm=Settings.llm,
    system_prompt="""You are a helpful assistant that can perform calculations
    and search through documents to answer questions.""",
)

# Now we can ask questions about the documents or do calculations
async def main():
    response = await agent.run(
        "What did the author do in college? Also, what's 7 * 8? Give complete answers to ALL questions asked."
    )
    print(response)


# Run the agent
if __name__ == "__main__":
    asyncio.run(main())