import { httpClient } from "./http";
import type { NodeCatalogItem, NodeSchemaResponse, NodeAuthoringSpec } from "./graph-authoring";
import type { ControlPlaneListResponse, ControlPlaneListView } from "./types";
import {
  ExecutablePipelineInputField,
  ExecutablePipelineInputSchema,
  ExecutablePipelineInputStep,
  PipelineStepExecution,
} from "@/components/pipeline/types";

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
  organization_id: string;
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

export interface PipelineToolBinding {
  enabled: boolean;
  tool_id?: string | null;
  tool_name: string;
  status?: string | null;
  description?: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  visual_pipeline_id?: string | null;
  executable_pipeline_id?: string | null;
}

export interface PipelineJob {
  id: string;
  organization_id: string;
  executable_pipeline_id: string;
  status: string;
  input_params: Record<string, unknown>;
  triggered_by: string;
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  created_at: string;
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
  async getJobSteps(jobId: string, organizationId?: string, lite: boolean = true): Promise<{ steps: PipelineStepExecution[] }> {
    const params = new URLSearchParams()
    if (organizationId) params.set("organization_id", organizationId)
    params.set("lite", String(lite))
    
    return httpClient.get<{ steps: PipelineStepExecution[] }>(`/admin/pipelines/jobs/${jobId}/steps?${params.toString()}`);
  }

  async getStepData(
    jobId: string,
    stepId: string,
    type: "input" | "output",
    page: number = 1,
    limit: number = 20,
    organizationId?: string
  ): Promise<PipelineStepData> {
    const params = new URLSearchParams();
    params.set("type", type);
    params.set("page", String(page));
    params.set("limit", String(limit));
    if (organizationId) params.set("organization_id", organizationId);
    
    return httpClient.get<PipelineStepData>(`/admin/pipelines/jobs/${jobId}/steps/${stepId}/data?${params.toString()}`);
  }

  async getStepFieldContent(
    jobId: string,
    stepId: string,
    type: "input" | "output",
    path: string,
    offset: number = 0,
    limit: number = 100000,
    organizationId?: string
  ): Promise<StepFieldContent> {
    const params = new URLSearchParams();
    params.set("type", type);
    params.set("path", path);
    params.set("offset", String(offset));
    params.set("limit", String(limit));
    if (organizationId) params.set("organization_id", organizationId);

    return httpClient.get<StepFieldContent>(`/admin/pipelines/jobs/${jobId}/steps/${stepId}/field?${params.toString()}`);
  }

  async getOperatorCatalog(
    pipelineType: "ingestion" | "retrieval",
    organizationId?: string,
  ): Promise<{ operators: NodeCatalogItem[] }> {
    const query = new URLSearchParams();
    query.set("pipeline_type", pipelineType);
    if (organizationId) query.set("organization_id", organizationId);
    const url = `/admin/pipelines/catalog?${query.toString()}`;
    return httpClient.get<{ operators: NodeCatalogItem[] }>(url);
  }

  async getOperatorSpec(operatorId: string, organizationId?: string): Promise<NodeAuthoringSpec> {
    const url = organizationId
      ? `/admin/pipelines/operators/${operatorId}?organization_id=${organizationId}`
      : `/admin/pipelines/operators/${operatorId}`;
    return httpClient.get<NodeAuthoringSpec>(url);
  }

  async listOperatorSpecs(
    pipelineType: "ingestion" | "retrieval",
    operatorIds: string[],
    organizationId?: string,
  ): Promise<NodeSchemaResponse> {
    const url = organizationId
      ? `/admin/pipelines/operators/schema?organization_id=${organizationId}`
      : "/admin/pipelines/operators/schema";
    return httpClient.post<NodeSchemaResponse>(url, {
      pipeline_type: pipelineType,
      operator_ids: operatorIds,
    });
  }

  async listVisualPipelines(
    organizationId?: string,
    params?: { skip?: number; limit?: number; view?: ControlPlaneListView }
  ): Promise<ControlPlaneListResponse<VisualPipeline>> {
    const query = new URLSearchParams();
    if (organizationId) query.set("organization_id", organizationId);
    query.set("skip", String(params?.skip ?? 0));
    query.set("limit", String(params?.limit ?? 20));
    query.set("view", params?.view ?? "summary");
    return httpClient.get<ControlPlaneListResponse<VisualPipeline>>(`/admin/pipelines/visual-pipelines?${query.toString()}`);
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
    organizationId?: string
  ): Promise<{ id: string; status: string }> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines?organization_id=${organizationId}`
      : "/admin/pipelines/visual-pipelines";
    return httpClient.post(url, data);
  }

  async getVisualPipeline(pipelineId: string, organizationId?: string): Promise<VisualPipeline> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?organization_id=${organizationId}`
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
    organizationId?: string
  ): Promise<{ status: string; version: number }> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}`;
    return httpClient.put(url, data);
  }

  async deleteVisualPipeline(pipelineId: string, organizationId?: string): Promise<{ status: string }> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}`;
    return httpClient.delete(url);
  }

  async compilePipeline(pipelineId: string, organizationId?: string): Promise<CompileResult> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/compile?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/compile`;
    return httpClient.post<CompileResult>(url, {});
  }

  async listPipelineVersions(
    pipelineId: string,
    organizationId?: string
  ): Promise<{ versions: ExecutablePipelineVersion[] }> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/versions?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/versions`;
    return httpClient.get<{ versions: ExecutablePipelineVersion[] }>(url);
  }

  async getExecutablePipeline(
    execId: string,
    organizationId?: string
  ): Promise<any> {
    const url = organizationId
      ? `/admin/pipelines/executable-pipelines/${execId}?organization_id=${organizationId}`
      : `/admin/pipelines/executable-pipelines/${execId}`;
    return httpClient.get<any>(url);
  }

  async getExecutablePipelineInputSchema(
    execId: string,
    organizationId?: string
  ): Promise<ExecutablePipelineInputSchema> {
    const url = organizationId
      ? `/admin/pipelines/executable-pipelines/${execId}/input-schema?organization_id=${organizationId}`
      : `/admin/pipelines/executable-pipelines/${execId}/input-schema`;
    return httpClient.get<ExecutablePipelineInputSchema>(url);
  }

  async getPipelineToolBinding(
    pipelineId: string,
    organizationId?: string
  ): Promise<PipelineToolBinding> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/tool-binding?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/tool-binding`;
    return httpClient.get<PipelineToolBinding>(url);
  }

  async updatePipelineToolBinding(
    pipelineId: string,
    data: {
      enabled: boolean;
      tool_name?: string;
      description?: string;
      input_schema?: Record<string, unknown>;
    },
    organizationId?: string
  ): Promise<PipelineToolBinding> {
    const url = organizationId
      ? `/admin/pipelines/visual-pipelines/${pipelineId}/tool-binding?organization_id=${organizationId}`
      : `/admin/pipelines/visual-pipelines/${pipelineId}/tool-binding`;
    return httpClient.put<PipelineToolBinding>(url, data);
  }

  async uploadPipelineInput(
    file: File,
    organizationId?: string
  ): Promise<{ path: string; filename?: string; upload_id?: string }> {
    const formData = new FormData();
    formData.append("file", file);
    const url = organizationId
      ? `/admin/pipelines/pipeline-inputs/upload?organization_id=${organizationId}`
      : "/admin/pipelines/pipeline-inputs/upload";
    return httpClient.post(url, formData);
  }

  async createPipelineJob(
    data: {
      executable_pipeline_id: string;
      input_params?: Record<string, Record<string, unknown>>;
    },
    organizationId?: string
  ): Promise<{ job_id: string; status: string; executable_pipeline_id: string }> {
    const url = organizationId
      ? `/admin/pipelines/jobs?organization_id=${organizationId}`
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
    organizationId?: string
  ): Promise<{ jobs: PipelineJob[]; total: number; page: number; pages: number }> {
    const params = new URLSearchParams();
    if (options?.executable_pipeline_id) params.set("executable_pipeline_id", options.executable_pipeline_id);
    if (options?.visual_pipeline_id) params.set("visual_pipeline_id", options.visual_pipeline_id);
    if (options?.status) params.set("status", options.status);
    if (options?.page) params.set("skip", String((options.page - 1) * (options?.limit || 20)));
    if (options?.limit) params.set("limit", String(options.limit));
    if (organizationId) params.set("organization_id", organizationId);
    return httpClient.get(`/admin/pipelines/jobs?${params.toString()}`);
  }

  async getPipelineJob(jobId: string, organizationId?: string): Promise<PipelineJob> {
    const url = organizationId
      ? `/admin/pipelines/jobs/${jobId}?organization_id=${organizationId}`
      : `/admin/pipelines/jobs/${jobId}`;
    return httpClient.get<PipelineJob>(url);
  }

}


export const ragAdminService = new RAGAdminService();
