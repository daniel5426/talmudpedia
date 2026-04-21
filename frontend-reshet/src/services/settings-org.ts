import { httpClient } from "./http"

export interface SettingsOrganization {
  id: string
  name: string
  status: string
  default_chat_model_id: string | null
  default_embedding_model_id: string | null
  default_retrieval_policy: string | null
}

class SettingsOrgService {
  async getOrganization(): Promise<SettingsOrganization> {
    return httpClient.get("/api/settings/organization")
  }

  async updateOrganization(input: Partial<SettingsOrganization>): Promise<SettingsOrganization> {
    return httpClient.patch("/api/settings/organization", input)
  }
}

export const settingsOrgService = new SettingsOrgService()
