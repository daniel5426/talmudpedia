# Backend State Overview

This document provides a comprehensive overview of the current state of the backend architecture, including a detailed file tree with descriptions for each component. 

## Architecture Highlights
- **Framework**: FastAPI (Async Python)
- **Database**: PostgreSQL (Supabase) via SQLAlchemy + AsyncPG
- **Agent Engine**: Custom `AgentCompiler` + LangGraph for declarative execution.
- **RAG**: Hybrid search (Vector + Keyword) using Qdrant/Pinecone/PGVector (Abstracted).
- **Authentication**: Usage of `AuthContext` dependency (transitioning from hardcoded legacy).

## File Tree & Descriptions

### `backend/app`
*Core application logic*

#### `backend/app/agent`
*Agent Domain: Definition, Compilation, and Execution*
- `config.py`: Pydantic models for agent configuration (LLM, Retrieval).
- `factory.py`: Factory class to instantiate agents from config (Legacy code-first approach).
- `langgraph_adapter.py`: Adapts LangGraph workflows to the streaming response interface.
- `tools.py`: Registry and definitions for agent tools.
- **`graph/`**
    - `compiler.py`: **Core Engine**. Compiles `AgentGraph` JSON into executable `StateGraph`.
    - `executable.py`: Runtime wrapper for executing/streaming compiled agents.
    - `schema.py`: Pydantic models defining the declarative Agent Graph (Nodes, Edges).
- **`core/`**
    - `base.py`: Abstract base class for agents.
    - `interfaces.py`: Abstract interfaces for LLMs, Retrievers, and Tools (Vendor agnostic).
    - `state.py`: TypedDict defining the state of an agent execution (messages, context, etc.).
- **`workflows/`**
    - `simple_rag.py`: Reference implementation of a specific RAG workflow.

#### `backend/app/api`
*API Interface Layer*
- `dependencies.py`: shared dependencies like `get_current_user` and `AuthContext`.
- **`routers/`**
    - `agents.py`: Endpoints for Agent CRUD, publishing, and execution/streaming.
    - `auth.py`: Authentication endpoints (Login, Callback).
    - `chat.py`: Chat interface endpoints (Conversation history, messages).
    - `collections.py`: Managing document collections for RAG.
    - `documents.py`: Document upload and management.
    - `models.py`: Managing logical `ModelRegistry` and provider bindings.
    - `org_units.py`: Organizational units management.
    - `projects.py`: Project-based isolation endpoints.
    - `rag_admin.py`: Administration for RAG pipelines and vector indices.
    - `rag_pipelines.py`: CRUD for RAG pipelines.
    - `search.py`: Search endpoints.
    - `tools.py`: Tool registry management endpoints.
    - `users.py`: User management endpoints.
    - `voice.py`: Voice agent REST endpoints.
    - `voice_ws.py`: WebSocket endpoints for real-time voice interaction (LiveKit).
- **`schemas/`**
    - `agents.py`: Schemas for agent API.
    - `rag.py`: Schemas for RAG and index management.
    - `common.py`: Shared API schemas.

#### `backend/app/core`
*Core Infrastructure & Config*
- `config.py`: Global application configuration (Env vars).
- `constants.py`: System-wide constants.
- `errors.py`: Custom exception classes.
- `logging.py`: Logging configuration.
- `security.py`: JWT utilities and password hashing.

#### `backend/app/db`
*Database Access Layer*
- `connection.py`: Database connection setup (SQLAlchemy engine & session).
- `session.py`: Database session context managers.
- `base.py`: Declarative base for SQLAlchemy models.
- **`postgres/models/`**
    - `agents.py`: DB Models for `Agent`, `AgentVersion`, `AgentRun`.
    - `chat.py`: DB Models for `ChatSession`, `ChatMessage`.
    - `files.py`: DB Models for uploaded files.
    - `identity.py`: DB Models for `User`, `Organization`, `Membership`.
    - `rag.py`: DB Models for `RAGPipeline`, `Document`.
    - `registry.py`: DB Models for `ModelRegistry`, `ToolRegistry`.
    - `voice.py`: DB Models for voice configs.

#### `backend/app/rag`
*Retrieval Augmented Generation Subsystem*
- `types.py`: Type definitions for RAG components.
- **`pipeline/`**
    - `compiler.py`: Compiles declarative RAG pipelines.
    - `component.py`: Base class for pipeline components.
- **`providers/`**
    - `loader/`: Document loaders (S3, etc.).
    - `vector_store/`: Vector DB implementations (PGVector, Pinecone, Qdrant).
    - `model/`: Embedding model wrappers.

#### `backend/app/services`
*Business Logic Layer*
- `agent_service.py`: **Agent Orchestration**. Manages agent lifecycle and execution (wires Compiler).
- `auth_service.py`: Authentication logic.
- `chat_service.py`: Manages chat sessions and history.
- `collection_service.py`: Logic for managing document collections.
- `document_service.py`: Logic for processing and chunking documents.
- `gemini_live.py`: Integration with Gemini Live API.
- `model_resolver.py`: Resolves logical model IDs to concrete providers.
- `rag_service.py`: RAG pipeline execution logic.
- `rag_admin_service.py`: Business logic for RAG administration and index management.
- `tool_service.py`: Management of available tools using `ToolRegistry`.
- `user_service.py`: User CRUD and management.
- **`voice/`**
    - `session_manager.py`: Manages WebRTC/WebSocket voice sessions.
- **`stt/`**: Speech-to-Text services (Google, etc.).

#### `backend/app/workers`
*Async Job Processing*
- `celery_app.py`: Celery application configuration.
- `tasks.py`: Definitions of async tasks (ingestion, processing).
- `job_manager.py`: Manager for tracking job status.
- `livekit_worker.py`: Worker for handling LiveKit voice events.

### `backend/scripts`
*Utility & Maintenance Scripts*
- `create_tables.py`: Script to initialize database tables.
- `migrate_rbac.py`: Migration script for moving RBAC data.
- (Various `debug_*.py` and `test_*.py` scripts for ad-hoc verification).

### `backend/tests`
*Test Suite*
- `conftest.py`: Test fixtures (DB session, async loop).
- `test_agent_compiler.py`: Unit tests for `AgentCompiler` and graph validation.
- `test_agent_service.py`: Tests for `AgentService` logic.
- `test_agents_router.py`: Integration tests for Agent API.

### `backend/` (Root)
- `main.py`: Application entry point (FastAPI app setup).
- `alembic/`: Database migration scripts.
- `requirements.txt`: Python dependencies.

### When update backend
- make shure you are updating this document file if its a change that need to be documented.
