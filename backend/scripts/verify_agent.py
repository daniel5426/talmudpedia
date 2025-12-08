import asyncio
import os
import sys
from unittest.mock import MagicMock

# Add current directory to path
sys.path.append(os.getcwd())

from langchain_core.messages import HumanMessage
from app.agent.workflows.advanced_rag import AdvancedRAGWorkflow
from app.agent.components.retrieval.vector import VectorRetriever
from app.agent.components.llm.openai import OpenAILLM

# Mock VectorRetriever
class MockRetriever(VectorRetriever):
    def __init__(self):
        pass
        
    async def retrieve(self, query: str, limit: int = 5, **kwargs):
        print(f"MockRetriever called with: {query}")
        # Return dummy docs
        doc = MagicMock()
        doc.content = "This is a test document about lost property."
        doc.metadata = {"ref": "Test Source"}
        doc.score = 0.9
        return [doc]

async def main():
    print("Starting verification...")
    
    # Set dummy env var if not present to avoid init errors
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-testing-structure-only"
    
    # Setup
    retriever = MockRetriever()
    llm = OpenAILLM(model="gpt-4o", api_key="sk-dummy") # Dummy wrapper with key
    
    # Instantiate workflow
    try:
        workflow = AdvancedRAGWorkflow(llm, retriever)
        print("Workflow instantiated.")
    except Exception as e:
        print(f"Failed to instantiate workflow: {e}")
        return
    
    # Compile graph
    try:
        workflow.compile()
        app = workflow.graph
        print("Graph compiled successfully.")
        # print(app.get_graph().draw_ascii())
    except Exception as e:
        print(f"Failed to compile graph: {e}")
        return
    
    # Check if we can run it (requires REAL API key)
    # We check if the key is the dummy one
    if os.environ["OPENAI_API_KEY"].startswith("sk-dummy"):
        print("Skipping execution test because OPENAI_API_KEY is a dummy.")
        print("Graph structure verification passed.")
        return

    # Run with a query
    print("\nRunning with query: 'What about lost property?'")
    inputs = {"messages": [HumanMessage(content="What about lost property?")]}
    
    try:
        async for event in app.astream(inputs):
            for key, value in event.items():
                print(f"\nNode '{key}':")
                if key == "tools":
                    print("Tool executed!")
                    # Verify tool output if possible
                    # print(value)
                if key == "agent":
                    print("Agent step completed.")
                    if "messages" in value:
                        msg = value["messages"][0]
                        print(f"Message type: {type(msg)}")
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            print(f"Tool calls: {msg.tool_calls}")
                        if hasattr(msg, "content") and msg.content:
                            print(f"Content: {msg.content[:50]}...")

    except Exception as e:
        print(f"Execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
