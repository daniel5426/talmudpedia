export * from "./types";
export { httpClient } from "./http";
export { authService } from "./auth";
export { chatService } from "./chat";
export { adminService } from "./admin";
export { ragAdminService } from "./rag-admin";
export type {
  RAGIndex, 
  RAGStats,
  RAGPipeline, 
  ChunkPreview, 
  VisualPipeline,
  VisualPipelineNode,
  VisualPipelineEdge,
  ExecutablePipelineVersion,
  CompilationError,
  CompileResult,
  PipelineJob,
  CustomOperator,
  PipelineStepData,
} from "./rag-admin";

export type {
  OperatorCatalog,
  OperatorCatalogItem,
  OperatorSpec,
  ConfigFieldSpec,
  PipelineStepExecution,
} from "@/components/pipeline/types";

export { ttsService } from "./tts";
export { sourceService } from "./source";
export { libraryService, normalizeLibraryQuery } from "./library";
export type {
  SourcePageData,
  MultiPageTextData,
  SinglePageTextData,
} from "./source";

export { orgUnitsService } from "./org-units";
export type { Tenant, TenantStatus, RetrievalPolicy, TenantSettings, OrgUnit, OrgUnitTree, OrgMember } from "./org-units";

export { rbacService } from "./rbac";
export type { Permission, Role, RoleAssignment, UserPermissions } from "./rbac";

export { auditService } from "./audit";
export type { AuditLog, AuditLogDetail, AuditFilters, ActionStats, ActorStats } from "./audit";
export { workloadSecurityService } from "./workload-security";
export type { ApprovalStatus, PendingScopePolicy, ActionApprovalDecision } from "./workload-security";

// Agent & Resource Services
export { agentService } from "./agent";
export { modelsService } from "./models";
export { toolsService } from "./tools";
export { credentialsService } from "./credentials";
export { publishedAppsService } from "./published-apps";
export { publishedRuntimeService } from "./published-runtime";

export type {
  Agent,
  AgentGraphDefinition,
  AgentRunStatus,
  AgentRunTreeResponse,
  AgentRunTreeNode,
  AgentRunTreeGroup,
  AgentRunTreeGroupMember,
  AgentExecutionEvent,
  AgentOperatorSpec,
  LogicalModel,
  ModelCapabilityType,
  ModelProviderType,
  ModelStatus,
  ModelProviderSummary,
  CreateModelRequest,
  UpdateModelRequest,
  CreateProviderRequest,
  UpdateProviderRequest,
  ModelsListResponse,
  ToolDefinition,
  ToolImplementationType,
  ToolStatus,
  ToolTypeBucket,
  CreateToolRequest,
  UpdateToolRequest,
  CreateBuiltinToolInstanceRequest,
  UpdateBuiltinToolInstanceRequest,
  ToolsListResponse,
} from "./agent";

export type {
  PublishedApp,
  PublishedAppTemplate,
  PublishedAppRevision,
  PublishedAppStatus,
  PublishedAppAuthProvider,
  BuilderPatchOp,
  BuilderStateResponse,
  BuilderValidationResponse,
  RevisionConflictResponse,
  CreatePublishedAppRequest,
  CreateBuilderRevisionRequest,
  UpdatePublishedAppRequest,
} from "./published-apps";

export type {
  PublishedRuntimeConfig,
  PublishedRuntimeAuthProvider,
  PublishedRuntimeUser,
  PublicAuthResponse,
  PublicChatHistory,
  PublicChatItem,
  PublishedRuntimeUI,
} from "./published-runtime";

export type {
  IntegrationCredential,
  IntegrationCredentialCategory,
  CreateCredentialRequest,
  UpdateCredentialRequest,
  CredentialStatus,
} from "./credentials";

// Knowledge Stores
export { knowledgeStoresService } from "./knowledge-stores";
export type {
  KnowledgeStore,
  CreateKnowledgeStoreRequest,
  UpdateKnowledgeStoreRequest,
  KnowledgeStoreStats,
} from "./knowledge-stores";
