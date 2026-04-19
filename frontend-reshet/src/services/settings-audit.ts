import { httpClient } from "./http"

export interface SettingsAuditLog {
  id: string
  actor_email: string
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  result: string
  failure_reason: string | null
  timestamp: string
  duration_ms: number | null
}

export interface SettingsAuditLogDetail extends SettingsAuditLog {
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
  request_params: Record<string, unknown> | null
}

export interface SettingsAuditFilters {
  actor_email?: string
  action?: string
  resource_type?: string
  resource_id?: string
  result?: string
  skip?: number
  limit?: number
}

class SettingsAuditService {
  async listAuditLogs(filters?: SettingsAuditFilters): Promise<SettingsAuditLog[]> {
    const params = new URLSearchParams()
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value))
      }
    })
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/settings/audit-logs${query}`)
  }

  async countAuditLogs(filters?: Omit<SettingsAuditFilters, "skip" | "limit">): Promise<{ count: number }> {
    const params = new URLSearchParams()
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, String(value))
      }
    })
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/api/settings/audit-logs/count${query}`)
  }

  async getAuditLog(logId: string): Promise<SettingsAuditLogDetail> {
    return httpClient.get(`/api/settings/audit-logs/${logId}`)
  }
}

export const settingsAuditService = new SettingsAuditService()
