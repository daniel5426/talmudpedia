# TalmudPedia Dynamic SDK

A code-first, schema-driven Python SDK for creating RAG and Agent pipelines programmatically.

## Key Features
- **Dynamic Discovery**: Instantly learns all available nodes (built-in & custom) from your backend.
- **SaaS-Ready**: Create custom tools/artifacts via API without needing local file access.
- **Unified Interface**: Use the same builder pattern for both RAG pipelines and Agents.

## Quick Start

### 1. Connection
```python
from backend.sdk import Client

# Initialize the client. It automatically fetches the catalog of nodes.
client = Client(base_url="http://localhost:8000", api_key="your_api_key")
```

### 2. Creating a Custom Artifact (Node)
Register a new tool that can be reused in any pipeline.
```python
from backend.sdk import ArtifactBuilder

python_code = """
from app.rag.pipeline.operator_executor import OperatorInput, OperatorOutput

def run(input_data: OperatorInput, config: dict) -> OperatorOutput:
    # Your custom logic here
    return OperatorOutput(success=True, data={"processed": True})
"""

ArtifactBuilder.create(
    client,
    name="my_custom_tool",
    display_name="Smart Processer",
    python_code=python_code
)

# Refresh client to see the new tool
client.connect()
```

### 3. Building a RAG Pipeline
```python
from backend.sdk import Pipeline

pipe = Pipeline("Document Ingestor")

# Access nodes dynamically via client.nodes.<category>.<NodeName>
loader = client.nodes.source.LocalLoader(base_path="/data/docs")
tool = client.nodes.custom.MyCustomTool() # Your artifact!
sink = client.nodes.storage.KnowledgeStoreSink(store="my-kb")

pipe.add(loader, tool, sink)
pipe.connect(loader, tool)
pipe.connect(tool, sink)

# Persist to platform
pipe.create(client)
```

### 4. Building an Agent
```python
from backend.sdk import Agent

agent = Agent("Customer Support")

start = client.agent_nodes.control.Input()
llm = client.agent_nodes.agent.Agent(model_id="gpt-4", system_prompt="Help the user.")

agent.add(start, llm)
agent.connect(start, llm)

agent.create(client, slug="customer-support-agent")
```

## Directory Structure
- `client.py`: Handles API communication and catalog fetching.
- `nodes.py`: Dynamic class factory that generates Python classes from JSON schemas.
- `pipeline.py`: DAG builder logic and serialization.
- `artifacts.py`: API wrapper for creating and promoting custom code artifacts.
