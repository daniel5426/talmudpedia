# Current Platform Status

## Agent Domain
- **Status**: Backend fully refactored to Service Layer pattern.
- **Service**: `AgentService` handles CRUD, validation, publishing, and execution orchestration.
- **Kernel**: `AgentCompiler` and `ExecutableAgent` handle LangGraph integration.
- **UI**: Agent List and Visual Builder are being restored.

## RAG Domain
- **Status**: Direct router-to-DB implementation.
- **Next Step**: Refactor to Service Layer pattern (Phase 3).

## Database
- **Primary**: PostgreSQL (Alembic managed).
- **Secondary**: MongoDB (Sefaria texts only).
- **Migration**: Schema partially populated; pending full data migration.
