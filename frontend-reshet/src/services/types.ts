export interface Citation {
  title: string;
  url: string;
  description: string;
  sourceRef?: string;
  ref?: string;
}

export interface MessageAttachmentPayload {
  name: string;
  type: string;
  content: string;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  reasoning_steps?: Array<{ step: string; status: string; message: string }>;
  tool_calls?: { 
    reasoning?: Array<{ step: string; status: string; message: string; citations?: Citation[]; query?: string; sources?: any[] }>;
    citations?: Citation[];
  };
  attachments?: MessageAttachmentPayload[];
}

export interface Chat {
  id: string;
  title: string;
  updated_at: string;
}

export interface ChatHistory {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
}

export interface ChatPagination {
  items: Chat[];
  nextCursor: string | null;
}

export interface ChatFetchParams {
  cursor?: string;
  limit?: number;
}

export interface User {
  id: string;
  email: string;
  full_name?: string;
  avatar?: string;
  role?: string;
  org_role?: string;
  tenant_id?: string;
  org_unit_id?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AdminStats {
  total_users: number;
  total_active_users: number;
  token_usage: Array<{ date: string; tokens: number }>;
  total_chats: number;
  total_chunks: number;
  total_messages: number;
  avg_messages_per_chat: number;
  estimated_tokens: number;
  new_users_last_7_days: number;
  daily_active_users: Array<{ date: string; count: number }>;
  daily_stats: Array<{ date: string; chats: number }>;
  top_users: Array<{ email: string; count: number }>;
  latest_chats: Array<{ id: string; title: string; created_at: string; user_email?: string }>;
}

export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  pages: number;
}

export interface ChatListResponse {
  items: Chat[];
  total: number;
  page: number;
  pages: number;
}

export interface UserDetailsResponse {
  user: User;
  stats: {
    chats_count: number;
    tokens_used_this_month: number;
  };
}

// --- Stats Types ---

export interface DailyDataPoint {
  date: string; // YYYY-MM-DD
  value: number;
}

export interface TopUserSummary {
  user_id: string;
  email: string;
  full_name?: string | null;
  count: number;
}

export interface ModelUsageSummary {
  model_name: string;
  message_count: number;
  token_count: number;
}

export interface PipelineUsageSummary {
  id: string;
  name: string;
  run_count: number;
  failed_count: number;
  failure_rate: number;
  last_run_at: string | null;
}

export interface AgentUsageSummary {
  id: string;
  name: string;
  slug: string;
  run_count: number;
  tokens_used: number;
}

export interface AgentFailureSummary {
  run_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  user_email?: string | null;
  error_message?: string | null;
  created_at: string;
}

export interface ProviderUsageSummary {
  provider: string;
  count: number;
}

export interface JobFailureSummary {
  id: string;
  pipeline_name: string;
  status: string;
  error_message?: string | null;
  created_at: string;
}

export interface AdminStatsOverview {
  total_users: number;
  active_users: number;
  total_chats: number;
  total_messages: number;
  total_tokens: number;
  estimated_spend_usd: number;
  new_users: number;
  avg_messages_per_chat: number;
  agent_runs: number;
  agent_runs_failed: number;
  pipeline_jobs: number;
  pipeline_jobs_failed: number;
  tokens_by_day: DailyDataPoint[];
  spend_by_day: DailyDataPoint[];
  daily_active_users: DailyDataPoint[];
  messages_by_role: Record<string, number>;
  top_users: TopUserSummary[];
  top_models: ModelUsageSummary[];
}

export interface KnowledgeStoreSummary {
  id: string;
  name: string;
  status: string;
  document_count: number;
  chunk_count: number;
  storage_backend: string;
  last_synced_at: string | null;
}

export interface PipelineSummary {
  id: string;
  name: string;
  pipeline_type: string;
  is_active: boolean;
  last_run_at: string | null;
  run_count: number;
}

export interface JobSummary {
  id: string;
  pipeline_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  chunk_count: number;
}

export interface AdminStatsRAG {
  knowledge_store_count: number;
  pipeline_count: number;
  total_chunks: number;
  stores_by_status: Record<string, number>;
  pipelines_by_type: Record<string, number>;
  avg_job_duration_ms: number | null;
  p95_job_duration_ms: number | null;
  knowledge_stores: KnowledgeStoreSummary[];
  pipelines: PipelineSummary[];
  recent_jobs: JobSummary[];
  top_pipelines: PipelineUsageSummary[];
  recent_failed_jobs: JobFailureSummary[];
  jobs_by_day: DailyDataPoint[];
  jobs_by_status: Record<string, number>;
}

export interface AgentSummary {
  id: string;
  name: string;
  slug: string;
  status: string;
  run_count: number;
  failed_count: number;
  last_run_at: string | null;
  avg_duration_ms: number | null;
}

export interface AdminStatsAgents {
  agent_count: number;
  total_runs: number;
  total_failed: number;
  failure_rate: number;
  avg_run_duration_ms: number | null;
  p95_run_duration_ms: number | null;
  avg_queue_time_ms: number | null;
  tokens_used_total: number;
  agents: AgentSummary[];
  top_agents: AgentSummary[];
  top_agents_by_tokens: AgentUsageSummary[];
  top_users_by_runs: TopUserSummary[];
  recent_failures: AgentFailureSummary[];
  runs_by_day: DailyDataPoint[];
  runs_by_status: Record<string, number>;
  tokens_by_day: DailyDataPoint[];
}

export interface ToolSummary {
  id: string;
  name: string;
  implementation_type: string;
  status: string;
}

export interface ModelSummary {
  id: string;
  name: string;
  slug: string;
  capability_type: string;
  status: string;
  provider_count: number;
}

export interface ArtifactSummary {
  id: string;
  name: string;
  category: string;
  version: string;
  is_active: boolean;
}

export interface AdminStatsResources {
  tool_count: number;
  model_count: number;
  artifact_count: number;
  tools_by_status: Record<string, number>;
  tools_by_type: Record<string, number>;
  models_by_capability: Record<string, number>;
  models_by_status: Record<string, number>;
  provider_bindings_by_provider: ProviderUsageSummary[];
  artifacts_by_category: Record<string, number>;
  artifacts_by_active: Record<string, number>;
  tools: ToolSummary[];
  models: ModelSummary[];
  artifacts: ArtifactSummary[];
}

export interface StatsSummaryResponse {
  section: string;
  period_days: number;
  generated_at: string;
  period_start: string;
  period_end: string;
  overview?: AdminStatsOverview;
  rag?: AdminStatsRAG;
  agents?: AdminStatsAgents;
  resources?: AdminStatsResources;
}

export type StatsSection = "overview" | "rag" | "agents" | "resources";
