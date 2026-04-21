import { httpClient } from "./http"
import type { SettingsMember } from "./settings-people-permissions"

export interface SettingsProject {
  id: string
  organization_id: string
  name: string
  description: string | null
  status: string
  is_default: boolean
  created_at: string
  member_count: number
}

class SettingsProjectsService {
  async listProjects(): Promise<SettingsProject[]> {
    return httpClient.get("/api/settings/projects")
  }

  async getProject(projectId: string): Promise<SettingsProject> {
    return httpClient.get(`/api/settings/projects/${projectId}`)
  }

  async createProject(input: { name: string; description?: string }): Promise<SettingsProject> {
    return httpClient.post("/api/settings/projects", input)
  }

  async updateProject(projectId: string, input: { name?: string; description?: string | null; status?: string }): Promise<SettingsProject> {
    return httpClient.patch(`/api/settings/projects/${projectId}`, input)
  }

  async listProjectMembers(projectId: string): Promise<SettingsMember[]> {
    return httpClient.get(`/api/settings/projects/${projectId}/members`)
  }
}

export const settingsProjectsService = new SettingsProjectsService()
