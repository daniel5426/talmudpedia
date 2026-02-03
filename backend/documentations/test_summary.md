# End-to-End Testing Summary (Tools, Agents, RAG)

Date: 2026-02-03
Tenant: danielbenassaya2626@gmail.com (real DB)

## Scope
This document summarizes the end-to-end tests executed across the three layers:
- Tools
- Agent nodes
- RAG pipelines (ingestion + retrieval)

It also lists the fixes applied during the testing process.

---

## What Was Tested

### 1) RAG Pipelines

#### A. Artifact-based Retrieval Pipelines (3 total)
Pipelines created and executed with the custom RAG artifacts:
- `retrieval-basic` (query_input → custom/rag_fake_retrieval → retrieval_result)
- `retrieval-with-passthrough` (query_input → custom/rag_query_passthrough → custom/rag_fake_retrieval → retrieval_result)
- `retrieval-alt-config` (query_input → custom/rag_fake_retrieval → retrieval_result with alternate config)

Validated:
- Compilation success
- Execution completion
- Step-level traces saved
- Output saved on the output node

#### B. Pinecone + OpenAI Pipelines (3 total)
Pipelines created and executed using real OpenAI embeddings + Pinecone vector store:

**Ingestion**
- `local_loader → recursive_chunker → model_embedder (OpenAI) → knowledge_store_sink (Pinecone)`

**Retrieval #1**
- `query_input → model_embedder (OpenAI) → vector_search (knowledge_store_id) → retrieval_result`

**Retrieval #2**
- `query_input → custom/rag_query_passthrough → model_embedder → vector_search → retrieval_result`

Validated:
- Pinecone index creation or reuse (existing index if max quota reached)
- Knowledge store creation
- Successful vector upserts
- Retrieval output in Pinecone namespace

---

### 2) Agent Nodes (3 builds + 1 OpenAI LLM agent)

#### A. Artifact / Tool Agents (3)

1. **Agent Echo**
- Graph: `start → transform → artifact:custom/agent_echo → end`
- Mapping coverage: complex template + upstream references

2. **Agent Defaults**
- Graph: `start → artifact:custom/agent_defaults → end`
- Mapping coverage: default mappings (no config or input mappings)

3. **Agent Tools**
- Graph: `start → tool_alpha → tool_beta → end`
- Mapping coverage: chained tool output → tool input

Validated:
- Graph compilation
- Execution completion
- Output state updates
- Trace persistence (on_chain_start / tool events)

#### B. OpenAI LLM Agent
- Graph: `start → llm (OpenAI) → end`
- Uses Model Registry + Provider Binding

Validated:
- Model resolution
- LLM execution
- Trace persistence

---

### 3) Tools

Custom artifact-backed tools:
- `custom/tool_alpha`
- `custom/tool_beta`

Validated:
- Tool registry persistence (fallback behavior if artifact columns missing)
- Tool invocation via artifact executor
- Input/output propagation into agent state

---

## What Was Fixed

### Frontend
1. **Agent Builder crashes when opening existing agents**
- Missing node `data` caused crashes (`executionStatus`, `category`, `config` undefined).
- Fix: normalize nodes on load + defensive guards in config and trace panels.

2. **Custom node config panels empty**
- Agent artifact config fields were not pulled dynamically.
- Fix: ConfigPanel now fetches `/agents/operators` and uses operator specs for config rendering.

3. **Agent Builder state crash**
- A `useEffect` was left outside component scope causing `setNodes is not defined`.
- Fix: moved normalization effect inside `AgentBuilderInner`.

Files updated:
- `frontend/src/components/agent-builder/AgentBuilder.tsx`
- `frontend/src/components/agent-builder/ConfigPanel.tsx`
- `frontend/src/components/agent-builder/nodes/BaseNode.tsx`

---

### Backend

1. **Vector search operator config mismatch**
- `vector_search` executor used wrong argument names.
- Fix: `top_k` instead of `limit`, `filter` instead of `filters`, and support for `knowledge_store_id`.

2. **Agent execution trace persistence issues**
- Duplicate trace inserts due to concurrency.
- Safeguards added (idempotent update, UUID handling).

3. **Tool registry schema mismatch in agent execution**
- Production DB missing `artifact_id` columns.
- Added fallback raw SQL query in tool executor.

4. **Tools API crash**
- `/tools` endpoint crashed when artifact columns missing.
- Fix: added fallback raw SQL query in `list_tools`.

5. **OpenAI Responses API compatibility**
- Some models reject `reasoning.effort` and encrypted content.
- Fix: fallback logic in OpenAI stream handler.

Files updated:
- `backend/app/rag/pipeline/operator_executor.py`
- `backend/app/agent/execution/service.py`
- `backend/app/agent/components/llm/openai.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/api/routers/tools.py`

---

## Artifacts Added (6 total)

Agent artifacts:
- `custom/agent_echo`
- `custom/agent_defaults`

Tool artifacts:
- `custom/tool_alpha`
- `custom/tool_beta`

RAG artifacts:
- `custom/rag_query_passthrough`
- `custom/rag_fake_retrieval`

---

## Test Files Created

- `backend/tests/test_full_artifact_layers.py`
- `backend/tests/test_pinecone_openai_rag.py`

---

## Notes / Gaps Identified

1. **Tool registry schema mismatch**
- DB missing `artifact_id` / `artifact_version` columns. Code now handles this, but schema migration is recommended.

2. **Trace persistence duplicates**
- Some duplicate insert warnings remain under high concurrency. A true DB-level UPSERT would be safer.

3. **Pinecone index quotas**
- Pinecone serverless project capped at 5 indexes. Tests now reuse an existing 1536-dimension index when needed.

---

## Output Visibility in Tenant
All pipelines, knowledge stores, agents, and models were created under:
- Tenant: `danielbenassaya2626@gmail.com`

Recent artifacts include:
- Pipelines: `Ingestion ...`, `Retrieval Basic ...`, `Retrieval Passthrough ...`
- Knowledge Stores: `Pinecone Store ...`
- Agents: `Agent Echo`, `Agent Defaults`, `Agent Tools`, `OpenAI Agent ...`
- Models: `OpenAI Embedding ...`, `OpenAI Chat ...`
