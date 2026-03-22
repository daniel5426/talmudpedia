import { httpClient } from "./http";
import { useAuthStore } from "@/lib/store/useAuthStore";

export type PublishedAppStatus = "draft" | "published" | "paused" | "archived";
export type PublishedAppVisibility = "public" | "private";
export type PublishedAppAuthProvider = "password" | "google";
export type PublishedAppRevisionKind = "draft" | "published";

export interface PublishedApp {
  id: string;
  tenant_id: string;
  agent_id: string;
  name: string;
  description?: string | null;
  logo_url?: string | null;
  slug: string;
  status: PublishedAppStatus;
  visibility: PublishedAppVisibility;
  auth_enabled: boolean;
  auth_providers: PublishedAppAuthProvider[];
  auth_template_key: string;
  template_key: string;
  current_draft_revision_id?: string | null;
  current_published_revision_id?: string | null;
  published_url?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
}

export interface PublishedAppStatsSeries {
  date: string;
  value: number;
}

export interface PublishedAppStatsSummary {
  app_id: string;
  start_date: string;
  end_date: string;
  approximate: boolean;
  visits: number;
  unique_visitors: number;
  agent_runs: number;
  failed_runs: number;
  tokens: number;
  threads: number;
  app_accounts: number;
  active_sessions: number;
  visits_by_day: PublishedAppStatsSeries[];
  runs_by_day: PublishedAppStatsSeries[];
  tokens_by_day: PublishedAppStatsSeries[];
  visit_surface_breakdown: Record<string, number>;
  visit_auth_state_breakdown: Record<string, number>;
}

export interface PublishedAppsStatsResponse {
  start_date: string;
  end_date: string;
  items: PublishedAppStatsSummary[];
}

export interface PublishedAppTemplate {
  key: string;
  name: string;
  description: string;
  thumbnail: string;
  tags: string[];
  entry_file: string;
  style_tokens: Record<string, string>;
}

export interface PublishedAppAuthTemplate {
  key: string;
  name: string;
  description: string;
  thumbnail: string;
  tags: string[];
  style_tokens: Record<string, string>;
}

export interface PublishedAppUser {
  app_account_id: string;
  user_id: string;
  global_user_id?: string | null;
  email: string;
  full_name?: string | null;
  avatar?: string | null;
  account_status: "active" | "blocked";
  membership_status: "active" | "blocked";
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
  active_sessions: number;
}

export interface PublishedAppDomain {
  id: string;
  host: string;
  status: "pending" | "approved" | "rejected";
  notes?: string | null;
  requested_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishedAppRevision {
  id: string;
  published_app_id: string;
  kind: PublishedAppRevisionKind;
  template_key: string;
  entry_file: string;
  files: Record<string, string>;
  build_status?: "queued" | "running" | "succeeded" | "failed";
  build_seq?: number;
  build_error?: string | null;
  build_started_at?: string | null;
  build_finished_at?: string | null;
  dist_storage_prefix?: string | null;
  dist_manifest?: Record<string, unknown> | null;
  template_runtime?: string;
  compiled_bundle?: string | null;
  bundle_hash?: string | null;
  version_seq?: number;
  origin_kind?: string;
  origin_run_id?: string | null;
  restored_from_revision_id?: string | null;
  source_revision_id?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface RevisionConflictResponse {
  code: "REVISION_CONFLICT";
  latest_revision_id: string;
  latest_updated_at: string;
  message: string;
}

export type BuilderPatchOp =
  | { op: "upsert_file"; path: string; content: string }
  | { op: "delete_file"; path: string }
  | { op: "rename_file"; from_path: string; to_path: string }
  | { op: "set_entry_file"; entry_file: string };

export interface BuilderStateResponse {
  app: PublishedApp;
  templates: PublishedAppTemplate[];
  current_draft_revision?: PublishedAppRevision | null;
  current_published_revision?: PublishedAppRevision | null;
  preview_token?: string | null;
  draft_dev?: DraftDevSessionResponse | null;
}

export type DraftDevSessionStatus =
  | "starting"
  | "building"
  | "serving"
  | "degraded"
  | "running"
  | "stopping"
  | "stopped"
  | "expired"
  | "error";

export function isDraftDevServingStatus(status?: DraftDevSessionStatus | null): boolean {
  return status === "serving" || status === "running";
}

export function isDraftDevPendingStatus(status?: DraftDevSessionStatus | null): boolean {
  return status === "starting" || status === "building" || status === "stopping";
}

export function isDraftDevFailureStatus(status?: DraftDevSessionStatus | null): boolean {
  return status === "degraded" || status === "error" || status === "expired";
}

export interface DraftDevSessionResponse {
  session_id: string;
  app_id: string;
  revision_id?: string | null;
  status: DraftDevSessionStatus;
  has_active_coding_runs: boolean;
  active_coding_run_count: number;
  preview_url?: string | null;
  preview_auth_token?: string | null;
  preview_auth_expires_at?: string | null;
  workspace_revision_token?: string | null;
  expires_at?: string | null;
  idle_timeout_seconds: number;
  last_activity_at?: string | null;
  last_error?: string | null;
}

export interface DraftDevSyncRequest {
  files?: Record<string, string>;
  entry_file?: string;
  operations?: BuilderPatchOp[];
  revision_id?: string;
}

export interface DraftDevHeartbeatResult {
  session: DraftDevSessionResponse | null;
  publish_locked: boolean;
  code?: string | null;
  message?: string | null;
  active_publish_job_id?: string | null;
}

export interface PublishJobResponse {
  job_id: string;
  app_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  source_revision_id?: string | null;
  saved_draft_revision_id?: string | null;
  published_revision_id?: string | null;
  error?: string | null;
  diagnostics: Array<{ message?: string; [key: string]: unknown }>;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export type PublishJobStatusResponse = PublishJobResponse;

export interface VersionPreviewRuntimeResponse {
  revision_id: string;
  preview_url: string;
  runtime_token: string;
  expires_at: string;
}

export interface CreatePublishedAppRequest {
  name: string;
  description?: string;
  logo_url?: string;
  slug?: string;
  agent_id: string;
  template_key: string;
  visibility?: PublishedAppVisibility;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
  auth_template_key?: string;
}

export interface UpdatePublishedAppRequest {
  name?: string;
  description?: string | null;
  logo_url?: string | null;
  slug?: string;
  agent_id?: string;
  visibility?: PublishedAppVisibility;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
  auth_template_key?: string;
  status?: PublishedAppStatus;
}

export interface UpdatePublishedAppUserRequest {
  membership_status: "active" | "blocked";
}

export interface CreatePublishedAppDomainRequest {
  host: string;
  notes?: string;
}

export interface CreateBuilderRevisionRequest {
  base_revision_id?: string;
  operations?: BuilderPatchOp[];
  files?: Record<string, string>;
  entry_file?: string;
}

export interface BuilderValidationResponse {
  ok: boolean;
  entry_file: string;
  file_count: number;
  diagnostics: Array<{ path?: string; message: string }>;
}

export interface PublishedAppExportOptions {
  supported: boolean;
  ready: boolean;
  template_key: string;
  source_kind?: string | null;
  default_archive_name: string;
  reason?: string | null;
}

export type CodingAgentDiagnostics = Array<{ message?: string; [key: string]: unknown }>;
export type CodingAgentExecutionEngine = "opencode";

export interface CodingAgentStreamEvent {
  event: string;
  run_id: string;
  app_id: string;
  seq: number;
  ts: string;
  stage: string;
  payload?: Record<string, unknown>;
  diagnostics?: CodingAgentDiagnostics;
}

export interface CodingAgentRun {
  run_id: string;
  status: string;
  execution_engine: CodingAgentExecutionEngine;
  chat_session_id?: string | null;
  surface?: string | null;
  published_app_id?: string | null;
  base_revision_id?: string | null;
  result_revision_id?: string | null;
  requested_model_id?: string | null;
  resolved_model_id?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  sandbox_id?: string | null;
  sandbox_status?: string | null;
  sandbox_started_at?: string | null;
}

export interface CodingAgentChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
}

export interface CodingAgentChatMessage {
  id: string;
  run_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface CodingAgentRunEvent {
  run_id: string;
  event: "tool.started" | "tool.completed" | "tool.failed";
  stage: string;
  payload: Record<string, unknown>;
  diagnostics: Array<Record<string, unknown>>;
  ts?: string | null;
}

export interface CodingAgentChatSessionDetail {
  session: CodingAgentChatSession;
  messages: CodingAgentChatMessage[];
  run_events?: CodingAgentRunEvent[];
  paging: {
    has_more: boolean;
    next_before_message_id?: string | null;
  };
}

export interface AppVersionListItem extends PublishedAppRevision {
  is_current_draft: boolean;
  is_current_published: boolean;
  run_status?: string | null;
  run_prompt_preview?: string | null;
}

export interface CodingAgentActiveRunState {
  run_id: string;
  status: string;
}

export interface CodingAgentPromptQueueItem {
  id: string;
  chat_session_id: string;
  position: number;
  status: string;
  input: string;
  client_message_id?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

export interface CodingAgentPromptSubmissionStartedResponse {
  submission_status: "started";
  run: CodingAgentRun;
}

export interface CodingAgentPromptSubmissionQueuedResponse {
  submission_status: "queued";
  active_run_id: string;
  queue_item: CodingAgentPromptQueueItem;
}

export type CodingAgentPromptSubmissionResponse =
  | CodingAgentPromptSubmissionStartedResponse
  | CodingAgentPromptSubmissionQueuedResponse;

export interface CodingAgentAnswerQuestionRequest {
  question_id: string;
  answers: string[][];
}

export const publishedAppsService = {
  async listStats(options: { days?: number; startDate?: string; endDate?: string } = {}): Promise<PublishedAppsStatsResponse> {
    const params = new URLSearchParams();
    if (options.days != null) {
      params.set("days", String(options.days));
    }
    if (options.startDate) {
      params.set("start_date", options.startDate);
    }
    if (options.endDate) {
      params.set("end_date", options.endDate);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return httpClient.get<PublishedAppsStatsResponse>(`/admin/apps/stats${suffix}`);
  },

  async list(): Promise<PublishedApp[]> {
    return httpClient.get<PublishedApp[]>("/admin/apps");
  },

  async listTemplates(): Promise<PublishedAppTemplate[]> {
    return httpClient.get<PublishedAppTemplate[]>("/admin/apps/templates");
  },

  async listAuthTemplates(): Promise<PublishedAppAuthTemplate[]> {
    return httpClient.get<PublishedAppAuthTemplate[]>("/admin/apps/auth/templates");
  },

  async get(appId: string): Promise<PublishedApp> {
    return httpClient.get<PublishedApp>(`/admin/apps/${appId}`);
  },

  async getStats(
    appId: string,
    options: { days?: number; startDate?: string; endDate?: string } = {},
  ): Promise<PublishedAppStatsSummary> {
    const params = new URLSearchParams();
    if (options.days != null) {
      params.set("days", String(options.days));
    }
    if (options.startDate) {
      params.set("start_date", options.startDate);
    }
    if (options.endDate) {
      params.set("end_date", options.endDate);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return httpClient.get<PublishedAppStatsSummary>(`/admin/apps/${appId}/stats${suffix}`);
  },

  async getBuilderState(appId: string): Promise<BuilderStateResponse> {
    return httpClient.get<BuilderStateResponse>(`/admin/apps/${appId}/builder/state`);
  },

  async create(payload: CreatePublishedAppRequest): Promise<PublishedApp> {
    return httpClient.post<PublishedApp>("/admin/apps", payload);
  },

  async update(appId: string, payload: UpdatePublishedAppRequest): Promise<PublishedApp> {
    return httpClient.patch<PublishedApp>(`/admin/apps/${appId}`, payload);
  },

  async remove(appId: string): Promise<{ status: string; id: string }> {
    return httpClient.delete<{ status: string; id: string }>(`/admin/apps/${appId}`);
  },

  async listUsers(appId: string): Promise<PublishedAppUser[]> {
    return httpClient.get<PublishedAppUser[]>(`/admin/apps/${appId}/users`);
  },

  async updateUser(appId: string, userId: string, payload: UpdatePublishedAppUserRequest): Promise<PublishedAppUser> {
    return httpClient.patch<PublishedAppUser>(`/admin/apps/${appId}/users/${userId}`, payload);
  },

  async listDomains(appId: string): Promise<PublishedAppDomain[]> {
    return httpClient.get<PublishedAppDomain[]>(`/admin/apps/${appId}/domains`);
  },

  async createDomain(appId: string, payload: CreatePublishedAppDomainRequest): Promise<PublishedAppDomain> {
    return httpClient.post<PublishedAppDomain>(`/admin/apps/${appId}/domains`, payload);
  },

  async deleteDomain(appId: string, domainId: string): Promise<{ status: string; id: string }> {
    return httpClient.delete<{ status: string; id: string }>(`/admin/apps/${appId}/domains/${domainId}`);
  },

  async getPublishJobStatus(appId: string, jobId: string): Promise<PublishJobStatusResponse> {
    return httpClient.get<PublishJobStatusResponse>(`/admin/apps/${appId}/publish/jobs/${jobId}`);
  },

  async unpublish(appId: string): Promise<PublishedApp> {
    return httpClient.post<PublishedApp>(`/admin/apps/${appId}/unpublish`, {});
  },

  async runtimePreview(appId: string): Promise<{ app_id: string; slug: string; status: string; runtime_url: string }> {
    return httpClient.get<{ app_id: string; slug: string; status: string; runtime_url: string }>(`/admin/apps/${appId}/runtime-preview`);
  },

  async listVersions(
    appId: string,
    options: { limit?: number; before_version_seq?: number } = {},
  ): Promise<AppVersionListItem[]> {
    const params = new URLSearchParams();
    if (options.limit != null) {
      params.set("limit", String(options.limit));
    }
    if (options.before_version_seq != null) {
      params.set("before_version_seq", String(options.before_version_seq));
    }
    const query = params.toString();
    const suffix = query ? `?${query}` : "";
    return httpClient.get<AppVersionListItem[]>(`/admin/apps/${appId}/versions${suffix}`);
  },

  async getVersion(appId: string, versionId: string): Promise<PublishedAppRevision> {
    return httpClient.get<PublishedAppRevision>(`/admin/apps/${appId}/versions/${versionId}`);
  },

  async getVersionPreviewRuntime(appId: string, versionId: string): Promise<VersionPreviewRuntimeResponse> {
    return httpClient.get<VersionPreviewRuntimeResponse>(`/admin/apps/${appId}/versions/${versionId}/preview-runtime`);
  },

  async createDraftVersion(appId: string, payload: CreateBuilderRevisionRequest): Promise<PublishedAppRevision> {
    return httpClient.post<PublishedAppRevision>(`/admin/apps/${appId}/versions/draft`, payload);
  },

  async restoreVersion(appId: string, versionId: string): Promise<PublishedAppRevision> {
    return httpClient.post<PublishedAppRevision>(`/admin/apps/${appId}/versions/${versionId}/restore`, {});
  },

  async publishVersion(appId: string, versionId: string): Promise<PublishJobResponse> {
    return httpClient.post<PublishJobResponse>(`/admin/apps/${appId}/versions/${versionId}/publish`, {});
  },

  async getDraftDevSession(appId: string): Promise<DraftDevSessionResponse> {
    return httpClient.get<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session`);
  },

  async ensureDraftDevSession(appId: string): Promise<DraftDevSessionResponse> {
    return httpClient.post<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session/ensure`, {});
  },

  async syncDraftDevSession(appId: string, payload: DraftDevSyncRequest): Promise<DraftDevSessionResponse> {
    return httpClient.patch<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session/sync`, payload);
  },

  async heartbeatDraftDevSession(appId: string): Promise<DraftDevSessionResponse> {
    return httpClient.post<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session/heartbeat`, {});
  },

  async heartbeatDraftDevSessionQuiet(appId: string): Promise<DraftDevHeartbeatResult> {
    const response = await httpClient.requestRaw(`/admin/apps/${appId}/builder/draft-dev/session/heartbeat`, {
      method: "POST",
      body: JSON.stringify({}),
    });

    if (response.ok) {
      return {
        session: await response.json() as DraftDevSessionResponse,
        publish_locked: false,
      };
    }

    let detail: unknown = null;
    try {
      const payload = await response.json();
      detail = (payload as { detail?: unknown } | null)?.detail ?? payload;
    } catch {
      detail = null;
    }

    if (response.status === 409 && detail && typeof detail === "object") {
      const detailObj = detail as Record<string, unknown>;
      const code = String(detailObj.code || "").trim();
      if (code.toUpperCase() === "PUBLISH_ACTIVE_SESSION_LOCKED") {
        return {
          session: null,
          publish_locked: true,
          code,
          message: String(detailObj.message || "").trim() || null,
          active_publish_job_id: String(detailObj.active_publish_job_id || "").trim() || null,
        };
      }
    }

    let message: unknown = "Heartbeat request failed";
    if (typeof detail === "string" && detail.trim()) {
      message = detail.trim();
    } else if (detail && typeof detail === "object") {
      message = JSON.stringify(detail);
    } else if (response.statusText) {
      message = response.statusText;
    }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  },

  async stopDraftDevSession(appId: string): Promise<DraftDevSessionResponse> {
    return httpClient.delete<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session`);
  },

  async validateRevision(appId: string, payload: CreateBuilderRevisionRequest): Promise<BuilderValidationResponse> {
    return httpClient.post<BuilderValidationResponse>(`/admin/apps/${appId}/builder/validate`, payload);
  },

  async resetTemplate(appId: string, templateKey: string): Promise<PublishedAppRevision> {
    return httpClient.post<PublishedAppRevision>(`/admin/apps/${appId}/builder/template-reset`, {
      template_key: templateKey,
    });
  },

  async getExportOptions(appId: string): Promise<PublishedAppExportOptions> {
    return httpClient.get<PublishedAppExportOptions>(`/admin/apps/${appId}/export/options`);
  },

  async downloadExportArchive(appId: string): Promise<{ blob: Blob; filename: string | null }> {
    const response = await httpClient.requestRaw(`/admin/apps/${appId}/export/archive`, {
      method: "POST",
    });
    if (!response.ok) {
      let message = "Export failed";
      try {
        const payload = await response.json() as { detail?: string; message?: string; error?: string };
        message = String(payload.detail || payload.message || payload.error || message);
      } catch {
        message = response.statusText || message;
      }
      throw new Error(message);
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename=\"?([^\";]+)\"?/i.exec(disposition);
    return {
      blob: await response.blob(),
      filename: match?.[1] || null,
    };
  },

  async submitCodingAgentPrompt(
    appId: string,
    payload: {
      input: string;
      model_id?: string | null;
      chat_session_id?: string;
      client_message_id?: string;
    },
  ): Promise<CodingAgentPromptSubmissionResponse> {
    return httpClient.post<CodingAgentPromptSubmissionResponse>(`/admin/apps/${appId}/coding-agent/v2/prompts`, payload);
  },

  async listCodingAgentChatSessions(appId: string, limit = 25): Promise<CodingAgentChatSession[]> {
    return httpClient.get<CodingAgentChatSession[]>(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions?limit=${encodeURIComponent(String(limit))}`,
    );
  },

  async getCodingAgentChatSession(
    appId: string,
    sessionId: string,
    options: { limit?: number; before_message_id?: string | null } = {},
  ): Promise<CodingAgentChatSessionDetail> {
    const params = new URLSearchParams();
    params.set("limit", String(Math.max(1, Number(options.limit || 10))));
    const beforeMessageId = String(options.before_message_id || "").trim();
    if (beforeMessageId) {
      params.set("before_message_id", beforeMessageId);
    }
    return httpClient.get<CodingAgentChatSessionDetail>(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions/${sessionId}?${params.toString()}`,
    );
  },

  async streamCodingAgentRun(
    appId: string,
    runId: string,
  ): Promise<Response> {
    // Bypass Next.js rewrite proxy for SSE because it can buffer chunked responses.
    const streamBase = String(process.env.NEXT_PUBLIC_BACKEND_STREAM_URL || "").trim();
    const backendBase = String(process.env.NEXT_PUBLIC_BACKEND_URL || "").trim();
    const directBackendUrl = /^https?:\/\//i.test(streamBase)
      ? streamBase
      : /^https?:\/\//i.test(backendBase)
        ? backendBase
        : "http://127.0.0.1:8026";
    const { useAuthStore } = await import("@/lib/store/useAuthStore");
    const authState = useAuthStore.getState();
    const token = authState.token;
    const tenantId = authState.user?.tenant_id;
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (tenantId) {
      headers["X-Tenant-ID"] = tenantId;
    }
    const url = new URL(
      `/admin/apps/${encodeURIComponent(appId)}/coding-agent/v2/runs/${encodeURIComponent(runId)}/stream`,
      directBackendUrl,
    );
    return fetch(url.toString(), {
      method: "GET",
      headers,
      credentials: "include",
    });
  },

  async getCodingAgentRun(appId: string, runId: string): Promise<CodingAgentRun> {
    return httpClient.get<CodingAgentRun>(`/admin/apps/${appId}/coding-agent/v2/runs/${runId}`);
  },

  async cancelCodingAgentRun(appId: string, runId: string): Promise<CodingAgentRun> {
    return httpClient.post<CodingAgentRun>(`/admin/apps/${appId}/coding-agent/v2/runs/${runId}/cancel`, {});
  },

  async answerCodingAgentRunQuestion(
    appId: string,
    runId: string,
    payload: CodingAgentAnswerQuestionRequest,
  ): Promise<CodingAgentRun> {
    return httpClient.post<CodingAgentRun>(
      `/admin/apps/${appId}/coding-agent/v2/runs/${runId}/answer-question`,
      payload,
    );
  },

  async getCodingAgentChatSessionActiveRun(appId: string, sessionId: string): Promise<CodingAgentActiveRunState> {
    return httpClient.get<CodingAgentActiveRunState>(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions/${sessionId}/active-run`,
    );
  },

  async findCodingAgentChatSessionActiveRun(
    appId: string,
    sessionId: string,
  ): Promise<CodingAgentActiveRunState | null> {
    const response = await httpClient.requestRaw(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions/${sessionId}/active-run`,
      { method: "GET" },
    );
    if (response.status === 404) {
      return null;
    }
    if (response.status === 401) {
      useAuthStore.getState().logout();
    }
    if (!response.ok) {
      let message = "Request failed";
      try {
        const data = await response.json();
        message = data?.detail || data?.message || message;
      } catch {
        message = response.statusText || message;
      }
      throw new Error(typeof message === "string" ? message : JSON.stringify(message));
    }
    return response.json() as Promise<CodingAgentActiveRunState>;
  },

  async listCodingAgentChatSessionQueue(appId: string, sessionId: string): Promise<CodingAgentPromptQueueItem[]> {
    return httpClient.get<CodingAgentPromptQueueItem[]>(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions/${sessionId}/queue`,
    );
  },

  async deleteCodingAgentChatSessionQueueItem(
    appId: string,
    sessionId: string,
    queueItemId: string,
  ): Promise<{ status: string; id: string }> {
    return httpClient.delete<{ status: string; id: string }>(
      `/admin/apps/${appId}/coding-agent/v2/chat-sessions/${sessionId}/queue/${queueItemId}`,
    );
  },

};
