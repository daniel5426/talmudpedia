import { httpClient } from "./http";

export type McpAuthMode = "none" | "static_bearer" | "static_headers" | "oauth_user_account";
export type McpApprovalPolicy = "ask" | "always_allow";

export interface McpServer {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  server_url: string;
  transport: string;
  auth_mode: McpAuthMode;
  is_active: boolean;
  auth_config: Record<string, unknown>;
  auth_metadata: Record<string, unknown>;
  capability_snapshot: Record<string, unknown>;
  oauth_client_id?: string | null;
  oauth_client_registration: Record<string, unknown>;
  tool_snapshot_version: number;
  sync_status: string;
  sync_error?: string | null;
  last_tested_at?: string | null;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
  has_static_bearer_token: boolean;
  has_static_headers: boolean;
  has_oauth_client_secret: boolean;
}

export interface McpDiscoveredTool {
  id: string;
  server_id: string;
  snapshot_version: number;
  name: string;
  title?: string | null;
  description?: string | null;
  input_schema: Record<string, unknown>;
  annotations: Record<string, unknown>;
  tool_metadata: Record<string, unknown>;
  created_at: string;
}

export interface McpAccountConnection {
  server_id: string;
  user_id: string;
  status: string;
  scopes: unknown[];
  account_metadata: Record<string, unknown>;
  last_error?: string | null;
  access_token_expires_at?: string | null;
  refresh_token_expires_at?: string | null;
  last_refreshed_at?: string | null;
  last_used_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface McpAgentMount {
  id: string;
  agent_id: string;
  server_id: string;
  applied_snapshot_version: number;
  approval_policy: McpApprovalPolicy;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateMcpServerRequest {
  name: string;
  description?: string;
  server_url: string;
  auth_mode: McpAuthMode;
  static_bearer_token?: string;
  static_headers?: Record<string, string>;
  auth_config?: Record<string, unknown>;
  oauth_client_id?: string;
  oauth_client_secret?: string;
  is_active?: boolean;
}

export type UpdateMcpServerRequest = Partial<CreateMcpServerRequest>;

export const mcpService = {
  listServers() {
    return httpClient.get<McpServer[]>("/mcp/servers");
  },

  getServer(id: string) {
    return httpClient.get<McpServer>(`/mcp/servers/${id}`);
  },

  createServer(payload: CreateMcpServerRequest) {
    return httpClient.post<McpServer>("/mcp/servers", payload);
  },

  updateServer(id: string, payload: UpdateMcpServerRequest) {
    return httpClient.patch<McpServer>(`/mcp/servers/${id}`, payload);
  },

  testServer(id: string) {
    return httpClient.post<Record<string, unknown>>(`/mcp/servers/${id}/test`, {});
  },

  syncServer(id: string) {
    return httpClient.post<Record<string, unknown>>(`/mcp/servers/${id}/sync`, {});
  },

  listTools(id: string, snapshotVersion?: number) {
    const suffix = snapshotVersion ? `?snapshot_version=${snapshotVersion}` : "";
    return httpClient.get<McpDiscoveredTool[]>(`/mcp/servers/${id}/tools${suffix}`);
  },

  startAuth(id: string) {
    return httpClient.post<{ authorization_url: string }>(`/mcp/servers/${id}/auth/start`, {});
  },

  getMyConnection(id: string) {
    return httpClient.get<McpAccountConnection | null>(`/mcp/servers/${id}/account/me`);
  },

  disconnectMyConnection(id: string) {
    return httpClient.delete<{ ok: boolean }>(`/mcp/servers/${id}/account/me`);
  },

  listAgentMounts(agentId: string) {
    return httpClient.get<McpAgentMount[]>(`/agents/${agentId}/mcp-mounts`);
  },

  createAgentMount(agentId: string, payload: { server_id: string; approval_policy?: McpApprovalPolicy }) {
    return httpClient.post<McpAgentMount>(`/agents/${agentId}/mcp-mounts`, payload);
  },

  updateAgentMount(agentId: string, mountId: string, payload: { approval_policy?: McpApprovalPolicy; is_active?: boolean; apply_latest_snapshot?: boolean }) {
    return httpClient.patch<McpAgentMount>(`/agents/${agentId}/mcp-mounts/${mountId}`, payload);
  },

  deleteAgentMount(agentId: string, mountId: string) {
    return httpClient.delete<{ ok: boolean }>(`/agents/${agentId}/mcp-mounts/${mountId}`);
  },
};
