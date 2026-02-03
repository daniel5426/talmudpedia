# Code Artifacts Architecture v1

## Overview
This document summarizes the architectural transition from database-stored custom operator code to a robust, file-based **Code Artifacts** system. This shift enables professional developer workflows, including version control, modularity, isolated testing, and optimized execution.

## Key Accomplishments

### 1. Artifact Registry Service
Implemented the `ArtifactRegistryService` in `backend/app/services/artifact_registry.py`.
- **Discovery**: Automatically scans the `backend/artifacts/` directory for `artifact.yaml` manifests.
- **Indexing**: Maintains a central registry of all available operators.
- **Versioning**: Supports multiple versions for the same artifact ID (e.g., `v1.0.0`, `v2.0.0`), allowing for safe migrations and pinned execution.

### 2. Runtime Execution Engine
Overhauled the `operator_executor.py` to support dynamic loading.
- **ArtifactExecutor**: Uses `importlib` to dynamically load Python modules from the filesystem.
- **Context Sandboxing**: Provides each executor with an `ArtifactContext` for secure and isolated access to inputs and configuration.
- **Bytecode Optimization**: Leverages Python's `__pycache__` for faster repeated execution compared to the legacy `exec()` on strings.

### 3. Developer Tooling & DX
Created a complete suite for local development:
- **CLI Scaffolder**: `backend/scripts/create_artifact.py` allows developers to quickly bootstrap new artifacts with standard directory structures (manifest, handler, tests, README).
- **Isolated Testing**: Integrated `pytest` support with a custom `artifact_context` fixture, allowing operators to be tested without running the full RAG pipeline.
- **Built-in Examples**: Established `builtin` namespace with the `html_cleaner` artifact as a reference implementation.

### 4. Browser-to-Artifact Workflow ("Promoted" Operators)
Bridged the gap between the UI and the filesystem:
- **Promotion API**: Added a backend endpoint to convert DB-stored drafts into persistent artifacts.
- **UI Integration**: Added a "Promote to Artifact" button (⚡️) in the Custom Operators dashboard.

### 5. Agent Artifact Integration (Phases 3 & 4)
Expanded the artifact system to support Agent nodes and Tools, making artifacts first-class citizens in the Agent Builder.
- **Scope & Categorization**: Extended `artifact.yaml` schema with `scope` (`rag` vs `agent`) and `category`, enabling distinct handling for different usage contexts.
- **Dynamic Node Registration**: Agents now dynamically discover and register artifact-based nodes at startup via the `AgentOperatorRegistry`.
- **First-Class Builder Support**: The Agent Builder frontend (`AgentBuilder.tsx`) now supports dynamic node types (e.g., `artifact:my_id`), allowing users to drag-and-drop filesystem artifacts alongside standard nodes.
- **Tool System Integration**: Updated `ToolRegistry` and `ToolNodeExecutor` to allow artifacts to be wrapped as callable Tools (`implementation_type: artifact`), enabling agents to use complex custom logic as tools.

## Technical Components Modified

### Backend
- `app/services/artifact_registry.py`: Core discovery logic updated to support scoping (`agent`/`rag`).
- `app/rag/pipeline/operator_executor.py`: RAG-specific execution handling.
- `app/agent/executors/artifact.py`: **[NEW]** specialized executor for Agent nodes with full observability.
- `app/agent/executors/tool.py`: Updated to delegate execution to artifacts.
- `app/agent/registry.py`: Dynamic registration of artifact operators.
- `app/api/routers/agents.py`: Added `/operators` endpoint for dynamic catalog serving.
- `app/api/routers/tools.py`: Updated schemas for artifact-backed tools.

### Frontend
- `components/agent-builder/NodeCatalog.tsx`: Fetches and displays dynamic artifact nodes.
- `components/agent-builder/AgentBuilder.tsx`: Logic for handling dynamic node types and props.
- `app/admin/tools/page.tsx`: UI for creating tools backed by artifacts.

## Future Roadmap
- **Hot-Patching**: Enable live updates without server restarts.
- **Remote Artifacts**: Support fetching artifacts from remote Git repositories.
- **Dependency Management**: Support `requirements.txt` per artifact for isolated environments.
