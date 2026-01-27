import { httpClient } from "./http";

export interface RAGStats {
  total_indices: number;
  live_indices: number;
  total_chunks: number;
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  running_jobs: number;
  total_pipelines?: number;
  compiled_pipelines?: number;
  active_pipeline_jobs?: number;
  available_providers: {
    embedding: string[];
    vector_store: string[];
    chunker: string[];
    loader: string[];
  };
}

export interface RAGIndex {
  name: string;
  display_name: string;
  dimension: number;
  total_vectors: number;
  namespaces: Record<string, number>;
  status: string;
  synced: boolean;
  owner_id?: string;
}

export interface RAGJob {
  id: string;
  index_name: string;
  source_type: string;
  source_path: string;
  namespace?: string;
  status: string;
  total_documents: number;
  processed_documents: number;
  total_chunks: number;
  upserted_chunks: number;
  failed_chunks: number;
  current_stage: string;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface JobProgress {
  job_id: string;
  status: string;
  current_stage: string;
  total_documents: number;
  processed_documents: number;
  total_chunks: number;
  upserted_chunks: number;
  failed_chunks: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  percent_complete: number;
}

export interface ChunkPreview {
  id: string;
  text: string;
  token_count: number;
  start_index: number;
  end_index: number;
}

export interface RAGPipeline {
  id: string;
  name: string;
  description?: string;
  embedding_provider: string;
  vector_store_provider: string;
  chunker_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  is_default: boolean;
  created_at: string;
}

export interface VisualPipelineNode {
  id: string;
  category: string;
  operator: string;
  position: { x: number; y: number };
  config: Record<string, unknown>;
}

export interface VisualPipelineEdge {
  id: string;
  source: string;
  target: string;
  source_handle?: string;
  target_handle?: string;
}

export interface VisualPipeline {
  id: string;
  tenant_id: string;
  org_unit_id?: string;
  name: string;
  description?: string;
  nodes: VisualPipelineNode[];
  edges: VisualPipelineEdge[];
  version: number;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExecutablePipelineVersion {
  id: string;
  version: number;
  is_valid: boolean;
  compiled_by?: string;
  created_at: string;
}

export interface CompilationError {
  code: string;
  message: string;
  node_id?: string;
}

export interface CompileResult {
  success: boolean;
  executable_pipeline_id?: string;
  version?: number;
  errors: CompilationError[];
  warnings: CompilationError[];
}

export interface PipelineJob {
  id: string;
  tenant_id: string;
  executable_pipeline_id: string;
  status: string;
  input_params: Record<string, unknown>;
  triggered_by: string;
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  created_at: string;
}

export interface PipelineStepExecution {
  id: string;
  job_id: string;
  step_id: string;
  operator_id: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  input_data?: any;
  output_data?: any;
  metadata: Record<string, any>;
  error_message?: string;
  execution_order: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface OperatorCatalog {
  source: OperatorCatalogItem[];
  normalization: OperatorCatalogItem[];
  enrichment: OperatorCatalogItem[];
  chunking: OperatorCatalogItem[];
  embedding: OperatorCatalogItem[];
  storage: OperatorCatalogItem[];
  retrieval: OperatorCatalogItem[];
  reranking: OperatorCatalogItem[];
  custom: OperatorCatalogItem[];
  transform: OperatorCatalogItem[];
}

export interface OperatorCatalogItem {
  operator_id: string;
  display_name: string;
  input_type: string;
  output_type: string;
  dimension?: number;
}

export interface ConfigFieldSpec {
  name: string;
  field_type: string;
  required: boolean;
  default?: unknown;
  description?: string;
  options?: string[];
}

export interface OperatorSpec {
  operator_id: string;
  display_name: string;
  category: string;
  input_type: string;
  output_type: string;
  required_config: ConfigFieldSpec[];
  optional_config: ConfigFieldSpec[];
  supports_parallelism: boolean;
  supports_streaming: boolean;
  dimension?: number;
}

export interface CustomOperator {
  id: string;
  tenant_id: string;
  name: string;
  display_name: string;
  category: string;
  description?: string;
  python_code: string;
  input_type: string;
  output_type: string;
  config_schema?: any[];
  is_active: boolean;
  version: string;
  created_at: string;
  updated_at: string;
  created_by?: string;
}

export interface CustomOperatorTestRequest {
  python_code: string;
  input_data: any;
  config: Record<string, any>;
  input_type: string;
  output_type: string;
}

export interface CustomOperatorTestResponse {
  success: boolean;
  data: any;
  error_message?: string;
  execution_time_ms: number;
}

class RAGAdminService {
  async getJobSteps(jobId: string, tenantSlug?: string): Promise<{ steps: PipelineStepExecution[] }> {
    const url = tenantSlug
      ? `/admin/pipelines/jobs/${jobId}/steps?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/jobs/${jobId}/steps`;
    return httpClient.get<{ steps: PipelineStepExecution[] }>(url);
  }

  async getStats(tenantSlug?: string): Promise<RAGStats> {
    const url = tenantSlug ? `/admin/rag/stats?tenant_slug=${tenantSlug}` : "/admin/rag/stats";
    return httpClient.get<RAGStats>(url);
  }

  async listIndices(tenantSlug?: string): Promise<{ indices: RAGIndex[] }> {
    const url = tenantSlug ? `/admin/rag/indices?tenant_slug=${tenantSlug}` : "/admin/rag/indices";
    return httpClient.get<{ indices: RAGIndex[] }>(url);
  }

  async createIndex(data: {
    name: string;
    display_name?: string;
    dimension?: number;
    namespace?: string;
    owner_id?: string;
  }, tenantSlug?: string): Promise<{ status: string; name: string; dimension: number }> {
    const url = tenantSlug ? `/admin/rag/indices?tenant_slug=${tenantSlug}` : "/admin/rag/indices";
    return httpClient.post(url, data);
  }

  async getIndex(name: string, tenantSlug?: string): Promise<RAGIndex> {
    const url = tenantSlug ? `/admin/rag/indices/${name}?tenant_slug=${tenantSlug}` : `/admin/rag/indices/${name}`;
    return httpClient.get<RAGIndex>(url);
  }

  async deleteIndex(name: string, tenantSlug?: string): Promise<{ status: string; name: string }> {
    const url = tenantSlug ? `/admin/rag/indices/${name}?tenant_slug=${tenantSlug}` : `/admin/rag/indices/${name}`;
    return httpClient.delete(url);
  }

  async chunkPreview(data: {
    text: string;
    chunk_size?: number;
    chunk_overlap?: number;
  }): Promise<{ total_chunks: number; chunks: ChunkPreview[] }> {
    return httpClient.post("/admin/rag/chunk-preview", data);
  }

  async ingestDocuments(data: {
    index_name: string;
    documents: Array<{ id?: string; text?: string; content?: string; metadata?: Record<string, any> }>;
    namespace?: string;
    embedding_provider?: string;
    vector_store_provider?: string;
    chunker_strategy?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    use_celery?: boolean;
  }, tenantSlug?: string): Promise<{ job_id: string; db_job_id?: string; status: string; message: string; websocket_url?: string }> {
    const url = tenantSlug ? `/admin/rag/ingest?tenant_slug=${tenantSlug}` : "/admin/rag/ingest";
    return httpClient.post(url, { use_celery: true, ...data });
  }

  async ingestFromLoader(data: {
    index_name: string;
    loader_type: string;
    source_path: string;
    namespace?: string;
    embedding_provider?: string;
    vector_store_provider?: string;
    chunker_strategy?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    loader_config?: Record<string, any>;
  }, tenantSlug?: string): Promise<{ job_id: string; status: string; message: string; websocket_url?: string }> {
    const url = tenantSlug ? `/admin/rag/ingest-from-loader?tenant_slug=${tenantSlug}` : "/admin/rag/ingest-from-loader";
    return httpClient.post(url, data);
  }

  async getJobProgress(jobId: string): Promise<JobProgress> {
    return httpClient.get<JobProgress>(`/admin/rag/jobs/${jobId}/progress`);
  }

  createJobWebSocket(jobId: string): WebSocket {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
    const wsUrl = backendUrl.replace(/^https?:/, protocol);
    return new WebSocket(`${wsUrl}/admin/rag/ws/jobs/${jobId}`);
  }

  createAllJobsWebSocket(): WebSocket {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
    const wsUrl = backendUrl.replace(/^https?:/, protocol);
    return new WebSocket(`${wsUrl}/admin/rag/ws/jobs`);
  }

  async listJobs(
    page = 1,
    limit = 20,
    status?: string,
    tenantSlug?: string
  ): Promise<{ items: RAGJob[]; total: number; page: number; pages: number }> {
    const skip = (page - 1) * limit;
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (status) params.set("status", status);
    if (tenantSlug) params.set("tenant_slug", tenantSlug);
    return httpClient.get(`/admin/rag/jobs?${params.toString()}`);
  }

  async getJob(jobId: string): Promise<RAGJob> {
    return httpClient.get<RAGJob>(`/admin/rag/jobs/${jobId}`);
  }

  async listPipelines(tenantSlug?: string): Promise<{ pipelines: RAGPipeline[] }> {
    const url = tenantSlug ? `/admin/rag/pipelines?tenant_slug=${tenantSlug}` : "/admin/rag/pipelines";
    return httpClient.get<{ pipelines: RAGPipeline[] }>(url);
  }

  async createPipeline(data: {
    name: string;
    description?: string;
    embedding_provider?: string;
    vector_store_provider?: string;
    chunker_strategy?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    is_default?: boolean;
    owner_id?: string;
  }, tenantSlug?: string): Promise<{ id: string; status: string }> {
    const url = tenantSlug ? `/admin/rag/pipelines?tenant_slug=${tenantSlug}` : "/admin/rag/pipelines";
    return httpClient.post(url, data);
  }

  async getOperatorCatalog(tenantSlug?: string): Promise<OperatorCatalog> {
    const url = tenantSlug 
      ? `/admin/pipelines/catalog?tenant_slug=${tenantSlug}` 
      : "/admin/pipelines/catalog";
    return httpClient.get<OperatorCatalog>(url);
  }

  async getOperatorSpec(operatorId: string, tenantSlug?: string): Promise<OperatorSpec> {
    const url = tenantSlug
      ? `/admin/pipelines/operators/${operatorId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/operators/${operatorId}`;
    return httpClient.get<OperatorSpec>(url);
  }

  async listOperatorSpecs(tenantSlug?: string): Promise<Record<string, OperatorSpec>> {
    const url = tenantSlug
      ? `/admin/pipelines/operators?tenant_slug=${tenantSlug}`
      : "/admin/pipelines/operators";
    return httpClient.get<Record<string, OperatorSpec>>(url);
  }

  async listVisualPipelines(tenantSlug?: string): Promise<{ pipelines: VisualPipeline[] }> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines?tenant_slug=${tenantSlug}`
      : "/admin/pipelines/visual-pipelines";
    return httpClient.get<{ pipelines: VisualPipeline[] }>(url);
  }

  async createVisualPipeline(
    data: {
      name: string;
      description?: string;
      nodes: VisualPipelineNode[];
      edges: VisualPipelineEdge[];
      org_unit_id?: string;
    },
    tenantSlug?: string
  ): Promise<{ id: string; status: string }> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines?tenant_slug=${tenantSlug}`
      : "/admin/pipelines/visual-pipelines";
    return httpClient.post(url, data);
  }

  async getVisualPipeline(pipelineId: string, tenantSlug?: string): Promise<VisualPipeline> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}`;
    return httpClient.get<VisualPipeline>(url);
  }

  async updateVisualPipeline(
    pipelineId: string,
    data: {
      name?: string;
      description?: string;
      nodes?: VisualPipelineNode[];
      edges?: VisualPipelineEdge[];
    },
    tenantSlug?: string
  ): Promise<{ status: string; version: number }> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}`;
    return httpClient.put(url, data);
  }

  async deleteVisualPipeline(pipelineId: string, tenantSlug?: string): Promise<{ status: string }> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}`;
    return httpClient.delete(url);
  }

  async compilePipeline(pipelineId: string, tenantSlug?: string): Promise<CompileResult> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/compile?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/compile`;
    return httpClient.post<CompileResult>(url, {});
  }

  async listPipelineVersions(
    pipelineId: string,
    tenantSlug?: string
  ): Promise<{ versions: ExecutablePipelineVersion[] }> {
    const url = tenantSlug
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/versions?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/versions`;
    return httpClient.get<{ versions: ExecutablePipelineVersion[] }>(url);
  }

  async createPipelineJob(
    data: {
      executable_pipeline_id: string;
      input_params?: Record<string, unknown>;
    },
    tenantSlug?: string
  ): Promise<{ job_id: string; status: string; executable_pipeline_id: string }> {
    const url = tenantSlug
      ? `/admin/pipelines/jobs?tenant_slug=${tenantSlug}`
      : "/admin/pipelines/jobs";
    return httpClient.post(url, data);
  }

  async listPipelineJobs(
    options?: {
      executable_pipeline_id?: string;
      status?: string;
      page?: number;
      limit?: number;
    },
    tenantSlug?: string
  ): Promise<{ jobs: PipelineJob[]; total: number; page: number; pages: number }> {
    const params = new URLSearchParams();
    if (options?.executable_pipeline_id) params.set("executable_pipeline_id", options.executable_pipeline_id);
    if (options?.status) params.set("status", options.status);
    if (options?.page) params.set("skip", String((options.page - 1) * (options?.limit || 20)));
    if (options?.limit) params.set("limit", String(options.limit));
    if (tenantSlug) params.set("tenant_slug", tenantSlug);
    return httpClient.get(`/admin/pipelines/jobs?${params.toString()}`);
  }

  async getPipelineJob(jobId: string, tenantSlug?: string): Promise<PipelineJob> {
    const url = tenantSlug
      ? `/admin/pipelines/jobs/${jobId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/jobs/${jobId}`;
    return httpClient.get<PipelineJob>(url);
  }

  async createCustomOperator(
    data: {
      name?: string;
      display_name: string;
      category: string;
      description?: string;
      python_code: string;
      input_type: string;
      output_type: string;
      config_schema?: any[];
    },
    tenantSlug?: string
  ): Promise<CustomOperator> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators?tenant_slug=${tenantSlug}`
      : "/admin/rag/custom-operators";
    return httpClient.post(url, data);
  }

  async listCustomOperators(tenantSlug?: string): Promise<CustomOperator[]> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators?tenant_slug=${tenantSlug}`
      : "/admin/rag/custom-operators";
    return httpClient.get<CustomOperator[]>(url);
  }

  async getCustomOperator(id: string, tenantSlug?: string): Promise<CustomOperator> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators/${id}?tenant_slug=${tenantSlug}`
      : `/admin/rag/custom-operators/${id}`;
    return httpClient.get<CustomOperator>(url);
  }

  async updateCustomOperator(
    id: string,
    data: Partial<Omit<CustomOperator, 'id' | 'tenant_id' | 'created_at' | 'updated_at' | 'created_by'>>,
    tenantSlug?: string
  ): Promise<CustomOperator> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators/${id}?tenant_slug=${tenantSlug}`
      : `/admin/rag/custom-operators/${id}`;
    return httpClient.put(url, data);
  }

  async deleteCustomOperator(id: string, tenantSlug?: string): Promise<{ status: string }> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators/${id}?tenant_slug=${tenantSlug}`
      : `/admin/rag/custom-operators/${id}`;
    return httpClient.delete(url);
  }

  async testCustomOperator(
    data: CustomOperatorTestRequest,
    tenantSlug?: string
  ): Promise<CustomOperatorTestResponse> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators/test?tenant_slug=${tenantSlug}`
      : "/admin/rag/custom-operators/test";
    return httpClient.post(url, data);
  }
}

export const ragAdminService = new RAGAdminService();
