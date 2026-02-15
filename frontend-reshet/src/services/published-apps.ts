import { httpClient } from "./http";

export type PublishedAppStatus = "draft" | "published" | "paused" | "archived";
export type PublishedAppAuthProvider = "password" | "google";
export type PublishedAppRevisionKind = "draft" | "published";

export interface PublishedApp {
  id: string;
  tenant_id: string;
  agent_id: string;
  name: string;
  slug: string;
  status: PublishedAppStatus;
  auth_enabled: boolean;
  auth_providers: PublishedAppAuthProvider[];
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
  slug?: string;
  agent_id: string;
  template_key: string;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
}

export interface UpdatePublishedAppRequest {
  name?: string;
  slug?: string;
  agent_id?: string;
  auth_enabled?: boolean;
  auth_providers?: PublishedAppAuthProvider[];
  status?: PublishedAppStatus;
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

type BuilderChatDiagnostics = Array<{ path?: string; message: string }>;

interface BuilderChatEventBase {
  event: string;
  stage: string;
  request_id: string;
  diagnostics?: BuilderChatDiagnostics;
}

export interface BuilderStatusEvent extends BuilderChatEventBase {
  event: "status";
  data: { content?: string };
}

export interface BuilderTokenEvent extends BuilderChatEventBase {
  event: "token";
  data: { content?: string };
}

export interface BuilderToolStartedEvent extends BuilderChatEventBase {
  event: "tool_started";
  data: {
    tool: string;
    iteration?: number;
    path?: string;
    command?: string;
  };
}

export interface BuilderToolCompletedEvent extends BuilderChatEventBase {
  event: "tool_completed";
  data: {
    tool: string;
    iteration?: number;
    status?: string;
    result?: Record<string, unknown>;
    command?: string;
  };
}

export interface BuilderToolFailedEvent extends BuilderChatEventBase {
  event: "tool_failed";
  data: {
    tool: string;
    iteration?: number;
    status?: string;
    result?: Record<string, unknown>;
    command?: string;
  };
}

export interface BuilderFileChangesEvent extends BuilderChatEventBase {
  event: "file_changes";
  data: {
    operations: BuilderPatchOp[];
    changed_paths?: string[];
    base_revision_id?: string;
    result_revision_id?: string;
    summary?: string;
    rationale?: string;
    assumptions?: string[];
  };
}

export interface BuilderCheckpointCreatedEvent extends BuilderChatEventBase {
  event: "checkpoint_created";
  data: {
    revision_id: string;
    source_revision_id?: string;
    checkpoint_type?: "auto_run" | "undo" | "file_revert" | string;
    checkpoint_label?: string;
  };
}

export interface BuilderDoneEvent extends BuilderChatEventBase {
  event: "done";
  type?: "done";
}

export interface BuilderErrorEvent extends BuilderChatEventBase {
  event: "error";
  data?: { message?: string };
}

export type BuilderChatEvent =
  | BuilderStatusEvent
  | BuilderTokenEvent
  | BuilderToolStartedEvent
  | BuilderToolCompletedEvent
  | BuilderToolFailedEvent
  | BuilderFileChangesEvent
  | BuilderCheckpointCreatedEvent
  | BuilderDoneEvent
  | BuilderErrorEvent;

export interface BuilderCheckpoint {
  turn_id: string;
  request_id: string;
  revision_id: string;
  source_revision_id?: string | null;
  checkpoint_type: "auto_run" | "undo" | "file_revert" | string;
  checkpoint_label?: string | null;
  assistant_summary?: string | null;
  created_at: string;
}

export interface UndoResponse {
  revision: PublishedAppRevision;
  restored_from_revision_id: string;
  checkpoint_turn_id: string;
  request_id: string;
}

export interface RevertFileRequest {
  path: string;
  from_revision_id: string;
  base_revision_id?: string;
}

export interface RevertFileResponse {
  revision: PublishedAppRevision;
  reverted_path: string;
  from_revision_id: string;
  request_id: string;
}

export const publishedAppsService = {
  async list(): Promise<PublishedApp[]> {
    return httpClient.get<PublishedApp[]>("/admin/apps");
  },

  async listTemplates(): Promise<PublishedAppTemplate[]> {
    return httpClient.get<PublishedAppTemplate[]>("/admin/apps/templates");
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

  async streamBuilderChat(appId: string, payload: { input: string; base_revision_id?: string }): Promise<Response> {
    return httpClient.requestRaw(`/admin/apps/${appId}/builder/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  },

  async getBuilderCheckpoints(appId: string, limit = 25): Promise<BuilderCheckpoint[]> {
    return httpClient.get<BuilderCheckpoint[]>(`/admin/apps/${appId}/builder/checkpoints?limit=${encodeURIComponent(String(limit))}`);
  },

  async undoLastBuilderRun(appId: string, payload: { base_revision_id?: string } = {}): Promise<UndoResponse> {
    return httpClient.post<UndoResponse>(`/admin/apps/${appId}/builder/undo`, payload);
  },

  async revertBuilderFile(appId: string, payload: RevertFileRequest): Promise<RevertFileResponse> {
    return httpClient.post<RevertFileResponse>(`/admin/apps/${appId}/builder/revert-file`, payload);
  },
};
