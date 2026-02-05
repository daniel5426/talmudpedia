# Stats API Documentation

Last Updated: 2026-02-05

## Overview
The Stats API provides platform-wide metrics and KPIs for the Admin Dashboard. It centralizes monitoring for users, chats, token usage, RAG performance, and agent runs.

## Backend Implementation

### Endpoint
- **URL**: `/api/v1/admin/stats/summary`
- **Method**: `GET`
- **Parameters**:
  - `section`: One of `overview`, `rag`, `agents`, `resources`.
  - `days`: Lookback period (default: 7, max: 90). Used when no explicit range is provided.
  - `start_date` (optional): ISO date or datetime string.
  - `end_date` (optional): ISO date or datetime string.
- **Authentication**: Requires Admin/Owner permissions.

### Models & Logic
- **Router**: `backend/app/api/routers/stats.py`
- **Schemas**: `backend/app/schemas/stats.py`
- **Logic**: Aggregates data from multiple tables (`User`, `Chat`, `Message`, `AgentRun`, `PipelineJob`, etc.) based on the requested section.

### Key Metrics
- **Overview**: Active users, total messages, estimated token spend, time-series for tokens/spend/DAU, message role breakdowns, top users, and model usage.
- **RAG**: Knowledge store status, pipeline run counts, job duration stats, top pipelines, and failed jobs.
- **Agents**: Run success/failure rates, duration and queue metrics, token usage trends, top agents by tokens, and failure summaries.
- **Resources**: Inventory of tools, models, and custom artifacts with breakdowns by status/type/category.

## Response Shape (High Level)
- `period_start`, `period_end`: Resolved range boundaries used for calculations.
- `period_days`: Number of days represented in the response.

### Overview Additions
- `new_users`, `avg_messages_per_chat`
- `daily_active_users`
- `messages_by_role`
- `top_users`
- `top_models`

### RAG Additions
- `stores_by_status`, `pipelines_by_type`
- `avg_job_duration_ms`, `p95_job_duration_ms`
- `top_pipelines`, `recent_failed_jobs`

### Agents Additions
- `avg_run_duration_ms`, `p95_run_duration_ms`, `avg_queue_time_ms`
- `tokens_used_total`, `tokens_by_day`
- `top_agents_by_tokens`, `top_users_by_runs`, `recent_failures`

### Resources Additions
- `tools_by_status`, `tools_by_type`
- `models_by_capability`, `models_by_status`
- `provider_bindings_by_provider`
- `artifacts_by_category`, `artifacts_by_active`

## Frontend Integration

### Service Layer
- **AdminService**: Logic resides in `src/services/admin.ts`.
- **Types**: Centralized in `src/services/types.ts` with the `AdminStats` prefix (e.g., `AdminStatsOverview`, `AdminStatsRAG`).

### Admin Dashboard
- **Page**: `frontend-reshet/src/app/admin/stats/page.tsx`.
- Uses a tabbed interface corresponding to the API sections.
- Supports preset ranges (7d/30d/90d) plus explicit date ranges.
- Clicking summary blocks opens detailed drilldowns with breadcrumb navigation.

## Architectural Standards
- **No Local Files**: Per `AGENTS.md`, stats types and API logic must never be defined locally within the page directory. Always use the `src/services` layer.
- **Type Safety**: All stats components must use the central `AdminStats` types to maintain consistency across the dashboard.
