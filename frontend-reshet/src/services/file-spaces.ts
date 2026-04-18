import { HttpRequestError, httpClient } from "./http"

export type FileAccessMode = "read" | "read_write"
export type FileEntryType = "file" | "directory"

export interface FileSpace {
  id: string
  tenant_id: string
  project_id: string
  name: string
  description: string | null
  status: "active" | "archived"
  file_count?: number | null
  total_bytes?: number | null
  created_at: string | null
  updated_at: string | null
}

export interface FileSpaceEntry {
  id: string
  space_id: string
  path: string
  name: string
  parent_path: string | null
  entry_type: FileEntryType
  current_revision_id: string | null
  mime_type: string | null
  byte_size: number | null
  sha256: string | null
  is_text: boolean
  deleted_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface FileEntryRevision {
  id: string
  entry_id: string
  storage_key: string
  mime_type: string
  byte_size: number
  sha256: string
  is_text: boolean
  encoding: string | null
  created_by: string | null
  created_by_run_id: string | null
  created_at: string | null
}

export interface AgentFileSpaceLink {
  id: string
  tenant_id: string
  project_id: string
  agent_id: string
  file_space_id: string
  access_mode: FileAccessMode
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface FileTextReadResponse {
  entry: FileSpaceEntry
  revision: FileEntryRevision
  content: string
}

class FileSpacesService {
  private readonly basePath = "/admin/files"

  async list(): Promise<{ items: FileSpace[] }> {
    return httpClient.get(`${this.basePath}`)
  }

  async get(spaceId: string): Promise<FileSpace> {
    return httpClient.get(`${this.basePath}/${spaceId}`)
  }

  async create(data: { name: string; description?: string | null }): Promise<FileSpace> {
    return httpClient.post(this.basePath, data)
  }

  async update(spaceId: string, data: { name?: string; description?: string | null }): Promise<FileSpace> {
    return httpClient.put(`${this.basePath}/${spaceId}`, data)
  }

  async archive(spaceId: string): Promise<void> {
    return httpClient.delete(`${this.basePath}/${spaceId}`)
  }

  async listTree(spaceId: string): Promise<{ items: FileSpaceEntry[] }> {
    return httpClient.get(`${this.basePath}/${spaceId}/tree`)
  }

  async mkdir(spaceId: string, path: string): Promise<{ entry: FileSpaceEntry }> {
    return httpClient.post(`${this.basePath}/${spaceId}/mkdir`, { path })
  }

  async readText(spaceId: string, path: string): Promise<FileTextReadResponse> {
    return httpClient.get(`${this.basePath}/${spaceId}/entries/content?path=${encodeURIComponent(path)}`)
  }

  async writeText(
    spaceId: string,
    data: { path: string; content: string; mime_type?: string | null },
  ): Promise<{ entry: FileSpaceEntry; revision: FileEntryRevision }> {
    return httpClient.put(`${this.basePath}/${spaceId}/entries/content`, data)
  }

  async patchText(
    spaceId: string,
    data: { path: string; old_text: string; new_text: string },
  ): Promise<{ entry: FileSpaceEntry; revision: FileEntryRevision }> {
    return httpClient.post(`${this.basePath}/${spaceId}/entries/patch`, data)
  }

  async uploadBlob(
    spaceId: string,
    data: { path: string; file: File },
  ): Promise<{ entry: FileSpaceEntry; revision: FileEntryRevision }> {
    const formData = new FormData()
    formData.set("path", data.path)
    formData.set("file", data.file)
    return httpClient.post(`${this.basePath}/${spaceId}/entries/upload`, formData)
  }

  async move(
    spaceId: string,
    data: { from_path: string; to_path: string },
  ): Promise<{ items: FileSpaceEntry[] }> {
    return httpClient.post(`${this.basePath}/${spaceId}/entries/move`, data)
  }

  async deleteEntry(spaceId: string, path: string): Promise<{ items: FileSpaceEntry[] }> {
    return httpClient.post(`${this.basePath}/${spaceId}/entries/delete`, { path })
  }

  async listRevisions(spaceId: string, path: string): Promise<{ items: FileEntryRevision[] }> {
    return httpClient.get(`${this.basePath}/${spaceId}/entries/revisions?path=${encodeURIComponent(path)}`)
  }

  buildDownloadUrl(spaceId: string, path: string): string {
    const baseUrl = httpClient.baseUrl || ""
    return `${baseUrl}${this.basePath}/${spaceId}/entries/download?path=${encodeURIComponent(path)}`
  }

  async fetchBlob(spaceId: string, path: string, options?: { signal?: AbortSignal }): Promise<Blob> {
    const response = await httpClient.requestRaw(
      `${this.basePath}/${spaceId}/entries/download?path=${encodeURIComponent(path)}`,
      { method: "GET", signal: options?.signal },
    )

    if (!response.ok) {
      let detail: unknown = null
      try {
        const payload = await response.json()
        detail = payload?.detail ?? payload
      } catch {
        detail = { message: response.statusText || "Request failed" }
      }

      throw new HttpRequestError(
        typeof detail === "string" ? detail : response.statusText || "Request failed",
        response.status,
        detail,
      )
    }

    return response.blob()
  }

  async listLinks(spaceId: string): Promise<{ items: AgentFileSpaceLink[] }> {
    return httpClient.get(`${this.basePath}/${spaceId}/links`)
  }

  async upsertLink(
    spaceId: string,
    data: { agent_id: string; access_mode: FileAccessMode },
  ): Promise<AgentFileSpaceLink> {
    return httpClient.post(`${this.basePath}/${spaceId}/links`, data)
  }

  async deleteLink(spaceId: string, agentId: string): Promise<void> {
    return httpClient.delete(`${this.basePath}/${spaceId}/links/${agentId}`)
  }
}

export const fileSpacesService = new FileSpacesService()
