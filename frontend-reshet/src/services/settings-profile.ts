import { httpClient } from "./http"

export interface SettingsProfile {
  id: string
  email: string
  full_name: string | null
  avatar: string | null
  role: string
}

class SettingsProfileService {
  async getProfile(): Promise<SettingsProfile> {
    return httpClient.get("/api/settings/profile")
  }

  async updateProfile(input: { full_name?: string | null; avatar?: string | null }): Promise<SettingsProfile> {
    return httpClient.patch("/api/settings/profile", input)
  }
}

export const settingsProfileService = new SettingsProfileService()
