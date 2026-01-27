export * from "./types";
export { httpClient } from "./http";
export { authService } from "./auth";
export { chatService } from "./chat";
export { adminService } from "./admin";
export { ragAdminService } from "./rag-admin";
export type { 
  RAGStats, 
  RAGIndex, 
  RAGPipeline, 
  ChunkPreview, 
  VisualPipeline,
  VisualPipelineNode,
  VisualPipelineEdge,
  ExecutablePipelineVersion,
  CompilationError,
  CompileResult,
  PipelineJob,
  OperatorCatalog,
  OperatorCatalogItem,
  OperatorSpec,
  ConfigFieldSpec,
  CustomOperator,
  PipelineStepExecution,
  PipelineStepData,
} from "./rag-admin";

export { ttsService } from "./tts";
export { sourceService } from "./source";
export { libraryService, normalizeLibraryQuery } from "./library";
export type {
  SourcePageData,
  MultiPageTextData,
  SinglePageTextData,
} from "./source";

export { orgUnitsService } from "./org-units";
export type { Tenant, OrgUnit, OrgUnitTree, OrgMember } from "./org-units";

export { rbacService } from "./rbac";
export type { Permission, Role, RoleAssignment, UserPermissions } from "./rbac";

export { auditService } from "./audit";
export type { AuditLog, AuditLogDetail, AuditFilters, ActionStats, ActorStats } from "./audit";

// Agent Resources (Models & Tools Registry)
export { modelsService, toolsService, agentService } from "./agent-resources";
export type {
  LogicalModel,
  ModelCapabilityType,
  ModelProviderType,
  ModelStatus,
  ModelProviderSummary,
  ToolDefinition,
  ToolImplementationType,
  ToolStatus,
  Agent,
} from "./agent-resources";

