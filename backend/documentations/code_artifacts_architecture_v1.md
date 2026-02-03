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

### 5. Unified Artifact Management UI
Refactored the administrative interface to provide a single entry point for all code logic across the platform.
- **Unified Explorer**: Consolidated Drafts (DB), Promoted (Files), and Built-in artifacts into a single "Code Artifacts" dashboard with differentiated status indicators.
- **Integrated IDE Experience**: A full-bleed code editor with a floating "Artifact Config" manifest bubble for editing metadata and JSON configuration schemas.
- **Live Test Runtime**: A dedicated "Test Console" providing real-time execution tracing, status badges, and performance metrics (ms).
- **Modern Navigation**: Promoted Artifacts to a top-level sidebar item, reflecting its role as a shared utility for RAG, Agents, and Tools.

### 6. Agent Artifact Integration (Phases 3 & 4)
Expanded the artifact system to support Agent nodes and Tools, making artifacts first-class citizens in the Agent Builder.
- **Scope & Categorization**: Extended `artifact.yaml` schema with `scope` (`rag` vs `agent`) and `category`, enabling distinct handling for different usage contexts.
- **Dynamic Node Registration**: Agents now dynamically discover and register artifact-based nodes at startup via the `AgentOperatorRegistry`.
- **First-Class Builder Support**: The Agent Builder frontend (`AgentBuilder.tsx`) now supports dynamic node types (e.g., `artifact:my_id`), allowing users to drag-and-drop filesystem artifacts alongside standard nodes.
- **Tool System Integration**: Updated `ToolRegistry` and `ToolNodeExecutor` to allow artifacts to be wrapped as callable Tools (`implementation_type: artifact`), enabling agents to use complex custom logic as tools.
    
### 7. Field Mapping Architecture (Phase 5)
Implemented a robust data-flow layer that decouples node execution from the global agent state, enabling predictable and reusable artifacts.
- **Explicit Input/Output Schemas**: Artifacts now declare structured `inputs` and `outputs` in their `artifact.yaml`, defining expected field names, types, and requirements.
- **FieldResolver Service**: A dedicated service (`field_resolver.py`) that resolves mapping expressions at runtime using `{{ ... }}` syntax.
- **Dynamic Expression Engine**: Supports sophisticated state traversal:
    - **State Access**: `{{ messages }}` or `{{ state.variables.my_var }}`.
    - **Upstream Referencing**: `{{ upstream.node_id.output_field }}` enables direct data pass-through between specific nodes.
    - **String Interpolation**: `The user said: {{ messages[-1].content }}`.
- **Validation Layer**: Built-in validation with strict/lenient modes ensures operators receive the correct data format, reducing runtime "silent failures".
- **Execution Lifecycle**: `ArtifactNodeExecutor` now automatically resolves inputs and captures outputs, storing them in `state._node_outputs` for downstream consumption.

## Technical Components Modified

### Backend
- `app/db/postgres/models/operators.py`: **[NEW]** Centralized model definition for `CustomOperator` and `OperatorCategory`, decoupled from `rag.py` to support multi-domain usage (Agents, Tools, RAG).
- `app/db/postgres/models/rag.py`: Removed direct definition of `CustomOperator` in favor of the shared model.
- `app/services/artifact_registry.py`: Core discovery logic updated to support scoping (`agent`/`rag`).
- `app/rag/pipeline/operator_executor.py`: RAG-specific execution handling.
- `app/agent/execution/field_resolver.py`: **[NEW]** Core engine for parsing `{{ mappings }}` and validating node inputs.
- `app/agent/executors/artifact.py`: Integrated `FieldResolver` to decouple handler execution from raw state.
- `app/agent/graph/compiler.py`: Updated to pass `input_mappings` and persist node outputs for upstream referencing.
- `app/agent/graph/schema.py`: Added `input_mappings` to `AgentNode` model.
- `app/api/routers/agents.py`: Added `/operators` endpoint for dynamic catalog serving.
- `app/api/routers/tools.py`: Updated schemas for artifact-backed tools.

### Frontend
- `app/admin/artifacts/page.tsx`: **[NEW]** Unified dashboard and editor for all artifact types.
- `services/artifacts.ts`: **[NEW]** Centralized service for CRUD, testing, and promotion logic.
- `components/app-sidebar.tsx`: Integrated top-level "Code Artifacts" navigation.
- `components/agent-builder/types.ts`: Extended with `inputMappings` and explicit artifact I/O types.
- `components/agent-builder/ConfigPanel.tsx`: **[UPDATE]** Added `field_mapping` editor and specialized input rendering.
- `components/agent-builder/NodeCatalog.tsx`: Fetches and displays dynamic artifact nodes.
- `components/agent-builder/AgentBuilder.tsx`: Logic for handling dynamic node types and props.
- `app/admin/tools/page.tsx`: UI for creating tools backed by artifacts.

## Future Roadmap
- **Hot-Patching**: Enable live updates without server restarts.
- **Remote Artifacts**: Support fetching artifacts from remote Git repositories.
- **Dependency Management**: Support `requirements.txt` per artifact for isolated environments.
