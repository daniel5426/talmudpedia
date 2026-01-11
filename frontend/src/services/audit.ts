import { httpClient } from "./http"

export interface AuditLog {
  id: string
  tenant_id: string
  org_unit_id: string | null
  actor_id: string
  actor_type: string
  actor_email: string
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  result: "success" | "failure" | "denied"
  failure_reason: string | null
  ip_address: string | null
  user_agent: string | null
  timestamp: string
  duration_ms: number | null
}

export interface AuditLogDetail extends AuditLog {
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
  request_params: Record<string, unknown> | null
}

export interface AuditFilters {
  actor_id?: string
  action?: string
  resource_type?: string
  resource_id?: string
  result?: string
  start_date?: string
  end_date?: string
  org_unit_id?: string
  skip?: number
  limit?: number
}

export interface ActionStats {
  [action: string]: {
    success: number
    failure: number
    denied: number
  }
}

export interface ActorStats {
  email: string
  action_count: number
  last_action: string
}

class AuditService {
  async listAuditLogs(
    tenantSlug: string,
    filters?: AuditFilters
  ): Promise<AuditLog[]> {
    const params = new URLSearchParams()
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined) {
          params.set(key, String(value))
        }
      })
    }
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/audit-logs${query}`)
  }

  async countAuditLogs(
    tenantSlug: string,
    filters?: Omit<AuditFilters, "skip" | "limit">
  ): Promise<{ count: number }> {
    const params = new URLSearchParams()
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined) {
          params.set(key, String(value))
        }
      })
    }
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/audit-logs/count${query}`)
  }

  async getAuditLog(tenantSlug: string, logId: string): Promise<AuditLogDetail> {
    return httpClient.get(`/api/tenants/${tenantSlug}/audit-logs/${logId}`)
  }

  async getActionStats(
    tenantSlug: string,
    filters?: { start_date?: string; end_date?: string }
  ): Promise<{ stats: ActionStats }> {
    const params = new URLSearchParams()
    if (filters?.start_date) params.set("start_date", filters.start_date)
    if (filters?.end_date) params.set("end_date", filters.end_date)
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/audit-logs/stats/actions${query}`)
  }

  async getActorStats(
    tenantSlug: string,
    filters?: { start_date?: string; end_date?: string; limit?: number }
  ): Promise<{ actors: ActorStats[] }> {
    const params = new URLSearchParams()
    if (filters?.start_date) params.set("start_date", filters.start_date)
    if (filters?.end_date) params.set("end_date", filters.end_date)
    if (filters?.limit) params.set("limit", String(filters.limit))
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/tenants/${tenantSlug}/audit-logs/stats/actors${query}`)
  }
}

export const auditService = new AuditService()
