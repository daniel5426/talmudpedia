# Tasks: MongoDB to PostgreSQL Migration

## Phase 1: Critical Fixes
- [x] Migrate `app/core/audit.py` to PostgreSQL <!-- id: 0 -->
- [x] Migrate `app/services/model_resolver.py` to PostgreSQL <!-- id: 1 -->
- [x] Migrate `app/api/routers/rag_pipelines.py` to PostgreSQL <!-- id: 2 -->
- [x] Create PostgreSQL models for Visual Pipelines <!-- id: 3 -->
- [x] Fix Pipeline Compiler dependencies <!-- id: 4 -->

## Phase 2: Voice Services
- [x] Migrate `app/services/voice/session_manager.py` to PostgreSQL <!-- id: 5 -->
- [x] Migrate `app/services/gemini_live.py` to PostgreSQL <!-- id: 6 -->

## Phase 3: Cleanup and Security
- [x] Address hardcoded credentials in `app/db/connection.py` <!-- id: 7 -->
- [x] Remove unused MongoDB models and references <!-- id: 8 -->
- [ ] Review performance and indexing <!-- id: 9 -->
- [x] Finalize Alembic migrations <!-- id: 10 -->
