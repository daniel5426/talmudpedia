# SDK Specification & Architecture (v1.0)

Last Updated: 2026-02-04

This document provides a technical specification for the TalmudPedia Dynamic Python SDK, intended for developers maintaining the platform or extending the SDK's capabilities.

## Architecture: Schema-Driven Discovery

The core philosophy of the SDK is **Zero Hardcoding**. It does not maintain a static list of available nodes. Instead, it relies on the Backend as the "Source of Truth" for capabilities.

### 1. Dynamic Registry Loading (`Client.connect()`)
Upon connection, the SDK performs two key GET requests:
- `/admin/pipelines/catalog`: Fetches all RAG operator specifications.
- `/agents/operators`: Fetches all Agent operator specifications.

These responses contain the full `OperatorSpec` for every node, including `json_schema` for configurations and metadata about I/O types.

### 2. Dynamic Class Factory (`NodeFactory`)
The `NodeFactory` uses Python's `type()` function to create classes at runtime. 
- **Namespacing**: Nodes are grouped into namespaces matching their category (e.g., `client.nodes.source`, `client.nodes.chunking`).
- **Class Generation**: `s3_loader` becomes `client.nodes.source.S3Loader`. Both the snake_case ID and CamelCase names are registered.
- **Attributes**: Every generated class inherits from `Node`, providing standard serialization (`to_dict`) and ID management.

### 3. DSL / Builder Pattern (`Pipeline` & `Agent`)
The SDK provides a Fluent API for constructing Directed Acyclic Graphs (DAGs).
- **ID Management**: Automatically generates UUIDs for nodes if not provided.
- **Edge Construction**: Simplifies edge definition `connect(source, target)` which handles the manual ID mapping required by the backend API.
- **Serialization**: The `to_payload()` method ensures the graph structure matches the `VisualPipeline` and `AgentGraph` schemas expected by the backend.

### 3.1 SDK Helpers (Agent Graphs)
- **`Client.from_env()`**: Initializes a client from `TEST_BASE_URL`, `TEST_API_KEY`, and `TEST_TENANT_ID`.
- **`Agent.execute()`**: Executes a created agent by ID (wraps `POST /agents/{agent_id}/execute`).
- **`GraphSpecValidator`**: Validates node configs against `config_schema` from the operator catalog.
- **`AgentGraphBuilder`**: Adds routing helpers for handles (`if_else`, `classify`, `while`, `user_approval`, `conditional`).
- **`GraphFuzzer`**: Generates randomized graphs for limit testing with optional config factories.

### 4. SaaS Remote Artifacts (`ArtifactBuilder`)
To support AI Agents that cannot access the host's local filesystem, the `ArtifactBuilder` bypasses file-based registration.
- **Method**: It hits the `POST /admin/rag/custom-operators` endpoint.
- **Persistence**: This registers the Python code directly into the PostgreSQL `custom_operators` table.
- **Real-time availability**: After creation, the `ArtifactBuilder` triggers a `client.connect()` refresh so the new node is immediately available as a Python attribute.

## Integration with AI Agents

This SDK is specifically designed to be "Agent-Consumable":
1. **Introspection**: An LLM can call `list(client.nodes.categories.keys())` to understand its domain.
2. **Standard Interfaces**: Because nodes are created from the same schema as the UI, an agent-built pipeline is indistinguishable from a human-built one.
3. **Execution**: Agents can write short Python scripts using this SDK to rapidly prototype new workflows without needing to understand the raw JSON API format.

## Future Roadmap

### Client-Side Validation
The `OperatorSpec` includes `config_schema`. The SDK now ships a `GraphSpecValidator` to validate configs *before* hitting the API. Future work should integrate validation directly into node instantiation and the builder flow for automatic checks.

### Versioning
Currently, the SDK pulls the default/latest version of operators. Future updates should support pinned versions for production stability.

### Async Support
The current SDK uses `requests`. For high-throughput environments or integration with async frameworks, an `aiohttp` based `AsyncClient` should be added.
