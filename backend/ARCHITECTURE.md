# Backend Architecture Overview

## System Purpose
A FastAPI-based backend for Talmudpedia, providing AI-powered chat capabilities with retrieval-augmented generation (RAG) over Jewish religious texts from the Sefaria library.

## Core Architecture

### 1. API Layer (`app/api/routers/`)
RESTful API endpoints organized by domain:
- **`auth.py`**: User authentication (register, login, JWT tokens)
- **`agent.py`**: AI chat endpoint with streaming responses
- **`chat.py`**: Chat history management (CRUD operations)
- **`texts.py`**: Text retrieval with complex reference navigation and pagination
- **`library.py`**: Library menu/tree serving
- **`search.py`**: Vector-based semantic search
- **`stt.py`**: Speech-to-text transcription
- **`general.py`**: Health checks and general utilities
- **`admin.py`**: Admin dashboard statistics and user management

### 2. Agent System (`app/agent/`)
Modular AI agent built on LangGraph:
- **`factory.py`**: Agent instantiation with dependency injection
- **`config.py`**: Configuration management
- **`workflows/`**: LangGraph workflow definitions
  - `advanced_rag.py`: Main RAG workflow with retrieval decision logic
- **`components/`**: Pluggable agent components
  - `llm/`: Language model providers (OpenAI, Google)
  - `retrieval/`: Vector (Pinecone), lexical (Elasticsearch), and hybrid retrievers
  - `tools/`: LangChain tools for text fetching and retrieval
- **`core/`**: Base abstractions and utilities

### 3. Service Layer (`app/services/`)
Business logic separated from endpoints:
- **`text/navigator.py`**: Complex text reference parsing and navigation
  - `ReferenceNavigator`: Parses Sefaria-style references (e.g., "Genesis 1:1", "Berakhot 2a")
  - `ComplexTextNavigator`: Handles hierarchical text structures (schemas)
- **`library/tree_builder.py`**: Builds hierarchical library menu from Sefaria API
- **`stt/`**: Speech-to-text providers (Google Cloud STT)

### 4. Database Layer (`app/db/`)
MongoDB integration with Pydantic models:
- **`connection.py`**: Async MongoDB client management
- **`models/`**: Pydantic schemas
  - `sefaria.py`: Text and index documents
  - `user.py`: User accounts
  - `chat.py`: Chat sessions and messages

### 5. Core Utilities (`app/core/`)
- **`security.py`**: Password hashing, JWT token generation/validation

### 6. External Services
- **`vector_store.py`** (root): Pinecone vector database wrapper with Google embeddings
- **Elasticsearch**: Lexical search for hybrid retrieval
- **MongoDB**: Primary data store for texts, users, chats
- **Sefaria API**: Source for Jewish text metadata and content

## Data Flow

### Chat Request Flow
1. Client sends message to `/chat` endpoint
2. `agent.py` validates user authentication
3. Message stored in MongoDB chat collection
4. Agent workflow (`AdvancedRAGWorkflow`) processes request:
   - Decides if retrieval is needed
   - If yes: Queries hybrid retriever (vector + lexical)
   - Reranks results
   - Generates response with LLM
5. Streams response tokens and reasoning steps to client
6. Saves assistant message with citations to MongoDB

### Text Retrieval Flow
1. Client requests text via `/api/source/{ref}`
2. `texts.py` parses reference using `ReferenceNavigator`
3. Queries MongoDB for best version (priority-based)
4. `ComplexTextNavigator` traverses schema tree to locate content
5. Constructs paginated response with context pages
6. Returns formatted text with Hebrew references

## Key Design Patterns
- **Dependency Injection**: Agent components are injected via factory pattern
- **Strategy Pattern**: Pluggable LLM and retrieval providers
- **Repository Pattern**: Database access abstracted through models
- **Service Layer**: Business logic separated from HTTP handlers
- **Streaming**: Server-sent events for real-time chat responses

## Technology Stack
- **Framework**: FastAPI (async Python web framework)
- **Agent**: LangGraph + LangChain
- **LLMs**: OpenAI GPT-4, Google Gemini
- **Vector DB**: Pinecone (serverless)
- **Search**: Elasticsearch
- **Database**: MongoDB (Motor async driver)
- **Auth**: JWT with bcrypt password hashing
- **Embeddings**: Google `gemini-embedding-001`

## Directory Structure
```
backend/
├── main.py                 # FastAPI app initialization
├── vector_store.py         # Pinecone wrapper
├── app/
│   ├── api/routers/        # HTTP endpoints
│   ├── agent/              # AI agent system
│   ├── services/           # Business logic
│   ├── db/                 # Database models & connection
│   └── core/               # Shared utilities
├── ingestion/              # Data ingestion scripts
└── scripts/                # Utility/debug scripts
```

## Scalability Considerations
- **Async I/O**: All database and external API calls are async
- **Stateless**: No server-side session state (JWT-based auth)
- **Serverless-ready**: Pinecone serverless, MongoDB Atlas compatible
- **Modular**: Components can be swapped (e.g., different LLM providers)
