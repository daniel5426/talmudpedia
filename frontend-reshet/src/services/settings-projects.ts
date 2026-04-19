import { httpClient } from "./http"
import type { SettingsMember } from "./settings-people-permissions"

export interface SettingsProject {
  id: string
  organization_id: string
  name: string
  slug: string
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

  async getProject(projectSlug: string): Promise<SettingsProject> {
    return httpClient.get(`/api/settings/projects/${projectSlug}`)
  }

  async createProject(input: { name: string; slug?: string; description?: string }): Promise<SettingsProject> {
    return httpClient.post("/api/settings/projects", input)
  }

  async updateProject(projectSlug: string, input: { name?: string; slug?: string; description?: string | null; status?: string }): Promise<SettingsProject> {
    return httpClient.patch(`/api/settings/projects/${projectSlug}`, input)
  }

  async listProjectMembers(projectSlug: string): Promise<SettingsMember[]> {
    return httpClient.get(`/api/settings/projects/${projectSlug}/members`)
  }
}

export const settingsProjectsService = new SettingsProjectsService()
