import { httpClient } from "./http"

export interface SettingsLimit {
  owner_scope: string
  owner_scope_id: string
  monthly_token_limit: number | null
  inherited_monthly_token_limit: number | null
  effective_monthly_token_limit: number | null
}

class SettingsLimitsService {
  async getOrganizationLimits(): Promise<SettingsLimit> {
    return httpClient.get("/api/settings/limits/organization")
  }

  async updateOrganizationLimits(input: { monthly_token_limit: number | null }): Promise<SettingsLimit> {
    return httpClient.patch("/api/settings/limits/organization", input)
  }

  async getProjectLimits(projectId: string): Promise<SettingsLimit> {
    return httpClient.get(`/api/settings/limits/projects/${projectId}`)
  }

  async updateProjectLimits(projectId: string, input: { monthly_token_limit: number | null }): Promise<SettingsLimit> {
    return httpClient.patch(`/api/settings/limits/projects/${projectId}`, input)
  }
}

export const settingsLimitsService = new SettingsLimitsService()
