import { httpClient } from './http'

// Types
export interface KnowledgeStore {
  id: string
  tenant_id: string
  name: string
  description: string | null
  embedding_model_id: string
  chunking_strategy: {
    strategy: string
    chunk_size?: number
    chunk_overlap?: number
    [key: string]: unknown
  }
  retrieval_policy: 'semantic_only' | 'hybrid' | 'keyword_only' | 'recency_boosted'
  backend: 'pinecone' | 'pgvector' | 'qdrant'
  status: 'initializing' | 'active' | 'syncing' | 'error' | 'archived'
  document_count: number
  chunk_count: number
  created_at: string
  updated_at: string
  created_by: string | null
}

export interface CreateKnowledgeStoreRequest {
  name: string
  description?: string
  embedding_model_id: string
  chunking_strategy?: {
    strategy?: string
    chunk_size?: number
    chunk_overlap?: number
  }
  retrieval_policy?: 'semantic_only' | 'hybrid' | 'keyword_only' | 'recency_boosted'
  backend?: 'pinecone' | 'pgvector' | 'qdrant'
  backend_config?: Record<string, unknown>
}

export interface UpdateKnowledgeStoreRequest {
  name?: string
  description?: string
  chunking_strategy?: {
    strategy?: string
    chunk_size?: number
    chunk_overlap?: number
  }
  retrieval_policy?: 'semantic_only' | 'hybrid' | 'keyword_only' | 'recency_boosted'
}

export interface KnowledgeStoreStats {
  document_count: number
  chunk_count: number
  index_stats: Record<string, unknown>
}

// Service
class KnowledgeStoresService {
  private basePath = '/admin/knowledge-stores'

  async list(tenantSlug?: string): Promise<KnowledgeStore[]> {
    const url = tenantSlug ? `${this.basePath}?tenant_slug=${tenantSlug}` : this.basePath
    return httpClient.get<KnowledgeStore[]>(url)
  }

  async get(id: string, tenantSlug?: string): Promise<KnowledgeStore> {
    const url = tenantSlug ? `${this.basePath}/${id}?tenant_slug=${tenantSlug}` : `${this.basePath}/${id}`
    return httpClient.get<KnowledgeStore>(url)
  }

  async create(data: CreateKnowledgeStoreRequest, tenantSlug?: string): Promise<KnowledgeStore> {
    const url = tenantSlug ? `${this.basePath}?tenant_slug=${tenantSlug}` : this.basePath
    return httpClient.post<KnowledgeStore>(url, data)
  }

  async update(id: string, data: UpdateKnowledgeStoreRequest, tenantSlug?: string): Promise<KnowledgeStore> {
    const url = tenantSlug ? `${this.basePath}/${id}?tenant_slug=${tenantSlug}` : `${this.basePath}/${id}`
    return httpClient.put<KnowledgeStore>(url, data)
  }

  async delete(id: string, tenantSlug?: string): Promise<void> {
    const url = tenantSlug ? `${this.basePath}/${id}?tenant_slug=${tenantSlug}` : `${this.basePath}/${id}`
    return httpClient.delete(url)
  }

  async getStats(id: string, tenantSlug?: string): Promise<KnowledgeStoreStats> {
    const url = tenantSlug ? `${this.basePath}/${id}/stats?tenant_slug=${tenantSlug}` : `${this.basePath}/${id}/stats`
    return httpClient.get<KnowledgeStoreStats>(url)
  }
}

export const knowledgeStoresService = new KnowledgeStoresService()
