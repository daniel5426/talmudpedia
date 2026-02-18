import { httpClient } from "./http";

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
  user_id: string;
  email: string;
  full_name?: string | null;
  avatar?: string | null;
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
  source_revision_id?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface RevisionBuildStatusResponse {
  revision_id: string;
  build_status: "queued" | "running" | "succeeded" | "failed";
  build_seq: number;
  build_error?: string | null;
  build_started_at?: string | null;
  build_finished_at?: string | null;
  dist_storage_prefix?: string | null;
  dist_manifest?: Record<string, unknown> | null;
  template_runtime?: string;
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

export type DraftDevSessionStatus = "starting" | "running" | "stopped" | "expired" | "error";

export interface DraftDevSessionResponse {
  session_id: string;
  app_id: string;
  revision_id?: string | null;
  status: DraftDevSessionStatus;
  preview_url?: string | null;
  expires_at?: string | null;
  idle_timeout_seconds: number;
  last_activity_at?: string | null;
  last_error?: string | null;
}

export interface DraftDevSyncRequest {
  files: Record<string, string>;
  entry_file: string;
  revision_id?: string;
}

export interface RevisionPreviewTokenResponse {
  revision_id: string;
  preview_token: string;
}

export interface PublishRequest {
  base_revision_id?: string;
  files?: Record<string, string>;
  entry_file?: string;
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

export interface PublishJobStatusResponse extends PublishJobResponse {}

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

export type CodingAgentDiagnostics = Array<{ message?: string; [key: string]: unknown }>;
export type CodingAgentExecutionEngine = "native" | "opencode";

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
  surface?: string | null;
  published_app_id?: string | null;
  base_revision_id?: string | null;
  result_revision_id?: string | null;
  checkpoint_revision_id?: string | null;
  requested_model_id?: string | null;
  resolved_model_id?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface CodingAgentCheckpoint {
  checkpoint_id: string;
  run_id: string;
  app_id: string;
  revision_id?: string | null;
  created_at: string;
}

export interface CodingAgentRestoreCheckpointResponse {
  checkpoint_id: string;
  revision: PublishedAppRevision;
  run_id?: string | null;
}

export const publishedAppsService = {
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

  async publish(appId: string, payload: PublishRequest = {}): Promise<PublishJobResponse> {
    return httpClient.post<PublishJobResponse>(`/admin/apps/${appId}/publish`, payload);
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

  async createRevision(appId: string, payload: CreateBuilderRevisionRequest): Promise<PublishedAppRevision> {
    return httpClient.post<PublishedAppRevision>(`/admin/apps/${appId}/builder/revisions`, payload);
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

  async stopDraftDevSession(appId: string): Promise<DraftDevSessionResponse> {
    return httpClient.delete<DraftDevSessionResponse>(`/admin/apps/${appId}/builder/draft-dev/session`);
  },

  async getRevisionBuildStatus(appId: string, revisionId: string): Promise<RevisionBuildStatusResponse> {
    return httpClient.get<RevisionBuildStatusResponse>(`/admin/apps/${appId}/builder/revisions/${revisionId}/build`);
  },

  async createRevisionPreviewToken(appId: string, revisionId: string): Promise<RevisionPreviewTokenResponse> {
    return httpClient.post<RevisionPreviewTokenResponse>(
      `/admin/apps/${appId}/builder/revisions/${revisionId}/preview-token`,
      {},
    );
  },

  async retryRevisionBuild(appId: string, revisionId: string): Promise<RevisionBuildStatusResponse> {
    return httpClient.post<RevisionBuildStatusResponse>(`/admin/apps/${appId}/builder/revisions/${revisionId}/build/retry`, {});
  },

  async validateRevision(appId: string, payload: CreateBuilderRevisionRequest): Promise<BuilderValidationResponse> {
    return httpClient.post<BuilderValidationResponse>(`/admin/apps/${appId}/builder/validate`, payload);
  },

  async resetTemplate(appId: string, templateKey: string): Promise<PublishedAppRevision> {
    return httpClient.post<PublishedAppRevision>(`/admin/apps/${appId}/builder/template-reset`, {
      template_key: templateKey,
    });
  },

  async createCodingAgentRun(
    appId: string,
    payload: {
      input: string;
      base_revision_id?: string;
      messages?: Array<{ role: string; content: string }>;
      model_id?: string | null;
      engine?: CodingAgentExecutionEngine;
    },
  ): Promise<CodingAgentRun> {
    return httpClient.post<CodingAgentRun>(`/admin/apps/${appId}/coding-agent/runs`, payload);
  },

  async streamCodingAgentRun(appId: string, runId: string): Promise<Response> {
    return httpClient.requestRaw(`/admin/apps/${appId}/coding-agent/runs/${runId}/stream`, {
      method: "GET",
      headers: {
        Accept: "text/event-stream",
      },
    });
  },

  async listCodingAgentCheckpoints(appId: string, limit = 25): Promise<CodingAgentCheckpoint[]> {
    return httpClient.get<CodingAgentCheckpoint[]>(
      `/admin/apps/${appId}/coding-agent/checkpoints?limit=${encodeURIComponent(String(limit))}`,
    );
  },

  async restoreCodingAgentCheckpoint(
    appId: string,
    checkpointId: string,
    payload: { run_id?: string } = {},
  ): Promise<CodingAgentRestoreCheckpointResponse> {
    return httpClient.post<CodingAgentRestoreCheckpointResponse>(
      `/admin/apps/${appId}/coding-agent/checkpoints/${checkpointId}/restore`,
      payload,
    );
  },
};
