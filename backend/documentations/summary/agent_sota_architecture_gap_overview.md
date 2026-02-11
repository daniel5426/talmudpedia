# SOTA Agent Architectures vs. Current Platform Fit

Last Updated: 2026-02-10

## Scope
This memo summarizes current state-of-the-art (SOTA) agent architecture patterns and assesses how the platform currently maps to those patterns. It includes codebase research findings and an abstract set of requirements to upgrade the platform for SOTA-style agents.

Sources (external):
- OpenAI Codex security docs
- Anthropic Claude Code security + settings (permissions, memory files) + MCP docs
- Model Context Protocol (MCP) documentation
- OpenCode docs (agents + LSP integration)

## Codebase Research (Evidence)
- `backend/app/agent/executors/standard.py`  
  `ReasoningNodeExecutor` parses JSON from model output, then manually invokes `ToolNodeExecutor`. There is an explicit TODO for tool binding.
- `backend/app/agent/executors/tool.py`  
  Tool execution supports `http`, `artifact`, `function`, `mcp`, `rag_retrieval`, and Built-in Tools v1 dispatch (`retrieval_pipeline`, `web_fetch`, `web_search`, `json_transform`, `datetime_utils`).
- `backend/app/agent/executors/rag.py`  
  Retrieval node execution is implemented and now shares runtime logic with retrieval tool execution via `retrieval_runtime.py`.
- `backend/app/agent/components/tools/retrieval_tool.py`  
  A LangChain-style retrieval tool exists but is not wired into the agent runtime.
- `backend/app/agent/core/llm_adapter.py` + `backend/app/agent/components/llm/*.py`  
  LLM providers do not expose tool binding; `bind_tools` is a passthrough with no provider-specific implementation.
- `backend/app/db/postgres/models/agents.py`  
  `memory_config` and `execution_constraints` are stored but not enforced in runtime.
- `backend/app/agent/execution/service.py`  
  Uses `langgraph.checkpoint.memory.MemorySaver` (in-memory) with no persistent checkpointer.
- `backend/app/db/postgres/models/registry.py` + `backend/app/api/routers/tools.py`  
  Tool registry and execution paths are implemented for MCP/function plus built-in template/instance APIs; production publish guardrails are enforced at runtime.

## SOTA Architecture Patterns (Today, External Research)
1. **Sandboxed, permissioned execution environment**
   - SOTA coding agents run in a sandbox with scoped filesystem access and controlled network permissions.
   - Permission prompts are first-class (read-only vs auto).  
   Sources: OpenAI Codex security docs; Claude Code security/sandboxing docs.

2. **Tooling via standardized protocols + fine-grained permissions**
   - MCP is used to integrate external tool servers.
   - Tool permissions can be allowlisted/denylisted in settings.  
   Sources: Claude Code settings + MCP docs; MCP specification.

3. **IDE/Language intelligence integration (LSP)**
   - SOTA coding agents integrate Language Server Protocol (LSP) for code intelligence.  
   Source: OpenCode LSP docs.

4. **Persistent, file-based memory / configuration**
   - Claude Code loads memory files (e.g., `CLAUDE.md`) and layered project/user settings.  
   Source: Claude Code settings.

5. **Multi-agent roles / subagents with scoped permissions**
   - SOTA systems define multiple agents with different permissions and responsibilities (e.g., Plan vs Build).  
   Source: OpenCode agents docs.

## Current Platform Fit (Observed in Code)
The platform already has strong pieces of a graph-based agent system, but tool usage inside agent nodes is still “prompt + parse” rather than true tool calling.

**Strengths today**
- **Graph orchestration** with many node types (start/agent/classify/logic/tool/RAG) and routing via `next`.
- **Pause/resume** for approval and human input via `interrupt_before`.
- **Execution events** (node start/end, tool start/end, token streaming) for UI traceability.
- **RAG pipelines** and vector search are implemented as first-class nodes.
- **Tool registry + runtime** support MCP/function/core built-ins with tenant-scoped execution.

**Gaps vs SOTA**
1. **Tool invocation is not native LLM tool calling**
   - Agent nodes do **not** bind tools to the LLM runtime. Tool calls are inferred by parsing JSON from text output.
2. **Tool invocation remains non-native**
   - Runtime tool execution exists, but agent reasoning still relies on parsed outputs rather than first-class provider-native tool-calling contracts.
3. **RAG as tool exists, but orchestration policy remains basic**
   - Retrieval is callable via built-in tooling, but advanced routing, policy, and observability patterns are still limited compared to SOTA systems.
4. **Memory and constraints are stored but not enforced**
   - `memory_config` and `execution_constraints` are not wired into runtime behavior.
5. **No standardized tool permission model**
   - There is no MCP server registry, permissions allowlist/denylist, or tool policy layer.
6. **No LSP-backed code intelligence**
   - There is no LSP integration to provide code diagnostics or navigation as tools.
7. **Checkpointing is in-memory only**
   - `MemorySaver` is used, so resumability is limited and non-durable.

## What This Means Practically
- The platform is **close in orchestration** (graph-level flow, approvals, observability), but not yet SOTA in **tool execution architecture**.
- Agents can be powerful, but their tool reliability depends on prompt adherence rather than enforceable tool contracts.

## Upgrade Demands (Abstract Requirements)
1. **Tool calling architecture**
   - Add native tool binding to LLM providers and route tool calls via model-side tool protocols.
   - Unify tool schemas and tool result typing across providers.
2. **Tool runtime + protocol governance**
   - Expand MCP/provider governance (registry, auth lifecycle, approvals), beyond the current execution bridge.
   - Harden sandbox/policy controls for function/artifact/networked built-ins.
3. **Permissions & safety**
   - Introduce per-tool permissions (allow/deny), read-only vs auto-execution modes, and explicit approval gates.
   - Enforce `execution_constraints` (token limits, timeouts, max iterations, concurrency).
4. **Memory & persistence**
   - Implement durable checkpointing (DB-backed) for pause/resume.
   - Wire `memory_config` into runtime, and add file-based memory ingestion (project/user scope).
5. **RAG/tool convergence**
   - Extend retrieval-tool policy/routing and surface richer traceability for retrieval decisions.
6. **Code intelligence**
   - Integrate LSP services and expose diagnostics/navigation as tools.
7. **Multi-agent roles**
   - Support role-based agents/subagents (Plan vs Build) with scoped tools/permissions and explicit handoffs.
8. **Observability & governance**
   - Expand execution traces to include tool policies, approvals, and tool call provenance for audits.

## Upgrade Roadmap (Phased)
**Phase 0: Alignment + Safety Envelope (1-2 sprints)**
- Define a unified tool schema contract (input, output, error model).
- Define tool permissions model (allow/ask/deny) and approval gates.
- Add runtime enforcement for `execution_constraints` (timeouts, max_tokens, max_iterations, concurrency).
- Decide on a persistent checkpointer interface (DB-backed) and run data retention policy.

**Phase 1: Native Tool Calling (2-4 sprints)**
- Implement tool binding in `LLMProvider` adapters for at least one provider.
- Replace JSON-parsing tool calls in `ReasoningNodeExecutor` with model tool call outputs.
- Normalize tool call event emission (start/end/error) with structured payloads.

**Phase 2: Tool Runtime Expansion (2-3 sprints)**
- Add MCP server governance (registry, allowlists, lifecycle) on top of existing execution path.
- Harden `function` and `artifact` execution with stricter sandbox/resource policy.
- Add policy controls for networked built-ins (`web_fetch`, `web_search`).

**Phase 3: Memory + Persistence (1-2 sprints)**
- Wire `memory_config` into runtime (short-term + optional long-term index).
- Add file-based memory ingestion (project/user scope).
- Switch from `MemorySaver` to a DB-backed checkpoint saver for durable resume.

**Phase 4: Retrieval Tool Maturity (1-2 sprints)**
- Expand retrieval tool routing/policies and metadata filters.
- Add richer retrieval provenance in traces/events.

**Phase 5: Code Intelligence (2-4 sprints)**
- Integrate LSP server management.
- Expose diagnostics/navigation as tools.

**Phase 6: Multi-Agent Roles (1-2 sprints)**
- Add Plan/Build/Explore-style subagents with scoped tool permissions.
- Support explicit agent handoffs in the graph/runtime.

## Minimum Viable SOTA (MV‑SOTA) Checklist
- Native tool calling for at least one provider (OpenAI or Anthropic).
- Tool permissions model with allow/ask/deny + approvals.
- MCP server registry/governance layer (execution path already exists).
- Durable checkpointing for pause/resume.
- Retrieval tool production hardening (callable path exists).
- File-based memory support with `memory_config` integration.
- LSP diagnostics tool available to agents.

## Open Questions
- Which provider gets first-class tool binding (OpenAI vs Anthropic)?
- What is the long-term memory store (Postgres, vector DB, or hybrid)?
- Should tool permissions be per-agent, per-run, or per-tenant defaults?
- Which RAG retrieval API should be the canonical tool interface (pipeline vs knowledge store)?
