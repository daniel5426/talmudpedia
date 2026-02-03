import { httpClient } from "./http";
import {
  ExecutablePipelineInputField,
  ExecutablePipelineInputSchema,
  ExecutablePipelineInputStep,
  OperatorCatalog,
  OperatorCatalogItem,
  OperatorSpec,
  PipelineStepExecution,
} from "@/components/pipeline/types";

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
  slug?: string;
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
  pipeline_type: "ingestion" | "retrieval";
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

export interface PipelineStepData {
  data: any;
  truncated_fields?: Record<string, {
    full_size: number;
    current_size: number;
    path: string;
    is_truncated: boolean;
  }>;
  total: number;
  page: number;
  pages: number;
  is_list: boolean;
}

export interface StepFieldContent {
  content: string;
  offset: number;
  limit: number;
  total_size: number;
  has_more: boolean;
  is_string: boolean;
}

class RAGAdminService {
  async getJobSteps(jobId: string, tenantSlug?: string, lite: boolean = true): Promise<{ steps: PipelineStepExecution[] }> {
    const params = new URLSearchParams()
    if (tenantSlug) params.set("tenant_slug", tenantSlug)
    params.set("lite", String(lite))
    
    return httpClient.get<{ steps: PipelineStepExecution[] }>(`/admin/pipelines/jobs/${jobId}/steps?${params.toString()}`);
  }

  async getStepData(
    jobId: string,
    stepId: string,
    type: "input" | "output",
    page: number = 1,
    limit: number = 20,
    tenantSlug?: string
  ): Promise<PipelineStepData> {
    const params = new URLSearchParams();
    params.set("type", type);
    params.set("page", String(page));
    params.set("limit", String(limit));
    if (tenantSlug) params.set("tenant_slug", tenantSlug);
    
    return httpClient.get<PipelineStepData>(`/admin/pipelines/jobs/${jobId}/steps/${stepId}/data?${params.toString()}`);
  }

  async getStepFieldContent(
    jobId: string,
    stepId: string,
    type: "input" | "output",
    path: string,
    offset: number = 0,
    limit: number = 100000,
    tenantSlug?: string
  ): Promise<StepFieldContent> {
    const params = new URLSearchParams();
    params.set("type", type);
    params.set("path", path);
    params.set("offset", String(offset));
    params.set("limit", String(limit));
    if (tenantSlug) params.set("tenant_slug", tenantSlug);

    return httpClient.get<StepFieldContent>(`/admin/pipelines/jobs/${jobId}/steps/${stepId}/field?${params.toString()}`);
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
      pipeline_type?: "ingestion" | "retrieval";
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
      pipeline_type?: "ingestion" | "retrieval";
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

  async getExecutablePipeline(
    execId: string,
    tenantSlug?: string
  ): Promise<any> {
    const url = tenantSlug
      ? `/admin/pipelines/executable-pipelines/${execId}?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/executable-pipelines/${execId}`;
    return httpClient.get<any>(url);
  }

  async getExecutablePipelineInputSchema(
    execId: string,
    tenantSlug?: string
  ): Promise<ExecutablePipelineInputSchema> {
    const url = tenantSlug
      ? `/admin/pipelines/executable-pipelines/${execId}/input-schema?tenant_slug=${tenantSlug}`
      : `/admin/pipelines/executable-pipelines/${execId}/input-schema`;
    return httpClient.get<ExecutablePipelineInputSchema>(url);
  }

  async uploadPipelineInput(
    file: File,
    tenantSlug?: string
  ): Promise<{ path: string; filename?: string; upload_id?: string }> {
    const formData = new FormData();
    formData.append("file", file);
    const url = tenantSlug
      ? `/admin/pipelines/pipeline-inputs/upload?tenant_slug=${tenantSlug}`
      : "/admin/pipelines/pipeline-inputs/upload";
    return httpClient.post(url, formData);
  }

  async createPipelineJob(
    data: {
      executable_pipeline_id: string;
      input_params?: Record<string, Record<string, unknown>>;
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
      visual_pipeline_id?: string;
      status?: string;
      page?: number;
      limit?: number;
    },
    tenantSlug?: string
  ): Promise<{ jobs: PipelineJob[]; total: number; page: number; pages: number }> {
    const params = new URLSearchParams();
    if (options?.executable_pipeline_id) params.set("executable_pipeline_id", options.executable_pipeline_id);
    if (options?.visual_pipeline_id) params.set("visual_pipeline_id", options.visual_pipeline_id);
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

  async promoteCustomOperator(
    id: string,
    namespace: string = "custom",
    tenantSlug?: string
  ): Promise<{ status: string; artifact_id: string; path: string; version: string }> {
    const url = tenantSlug
      ? `/admin/rag/custom-operators/${id}/promote?tenant_slug=${tenantSlug}&namespace=${namespace}`
      : `/admin/rag/custom-operators/${id}/promote?namespace=${namespace}`;
    return httpClient.post(url, {});
  }
}


export const ragAdminService = new RAGAdminService();
