import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.ollama import Ollama
from llama_index.core.workflow import Context

# Define a simple calculator tool
def multiply(a: float, b: float) -> float:
    """Useful for multiplying two numbers."""
    result = float(a) * float(b)
    # print(f"Multiplying {a} and {b} gives {result}")
    return result

# Define a simple calculator tool
def add(a: float, b: float) -> float:
    """Useful for adding two numbers."""
    result = float(a) + float(b)
    # print(f"Adding {a} and {b} gives {result}")
    return result

# Create an agent workflow with our calculator tool
agent = FunctionAgent(
    tools=[multiply, add],
    llm=Ollama(
        model="llama3.2",
        request_timeout=360.0,
        # Manually set the context window to limit memory usage
        context_window=8000,
    ),
    system_prompt="You are a helpful assistant that can multiply or add two numbers. Only provide final answer",
)


ctx = Context(agent)

async def main():
    # Run the agent
    response = await agent.run("My name is Kalyan.", ctx=ctx)
    response = await agent.run("What is 1234 * 4567?", ctx=ctx)
    print(str(response))
    response = await agent.run("What is 1+1? what is my name?", ctx=ctx)
    print(str(response))

# Run the agent
if __name__ == "__main__":
    asyncio.run(main())