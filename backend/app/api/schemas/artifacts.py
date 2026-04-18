from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

class ArtifactType(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ArtifactKind(str, Enum):
    AGENT_NODE = "agent_node"
    RAG_OPERATOR = "rag_operator"
    TOOL_IMPL = "tool_impl"


class ArtifactLanguage(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"


class ArtifactOwnerType(str, Enum):
    TENANT = "tenant"
    SYSTEM = "system"


class ArtifactSourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    content: str


class ArtifactRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: ArtifactLanguage = ArtifactLanguage.PYTHON
    source_files: list[ArtifactSourceFile]
    entry_module_path: str
    dependencies: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("dependencies", "python_dependencies"),
    )
    runtime_target: str = "cloudflare_workers"


class ArtifactCapabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network_access: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)
    secret_refs: list[str] = Field(default_factory=list)
    storage_access: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)


class AgentArtifactContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state_reads: list[str] = Field(default_factory=list)
    state_writes: list[str] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    node_ui: Dict[str, Any] = Field(default_factory=dict)


class RAGArtifactContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_category: str
    pipeline_role: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = "background"


class ToolArtifactContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: list[str] = Field(default_factory=list)
    execution_mode: str = "interactive"
    tool_ui: Dict[str, Any] = Field(default_factory=dict)


class ArtifactContractEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ArtifactKind
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None

    @model_validator(mode="after")
    def validate_contract_shape(self) -> "ArtifactContractEnvelope":
        if self.kind == ArtifactKind.AGENT_NODE:
            if self.agent_contract is None or self.rag_contract is not None or self.tool_contract is not None:
                raise ValueError("agent_node artifacts require only agent_contract")
        elif self.kind == ArtifactKind.RAG_OPERATOR:
            if self.rag_contract is None or self.agent_contract is not None or self.tool_contract is not None:
                raise ValueError("rag_operator artifacts require only rag_contract")
        elif self.kind == ArtifactKind.TOOL_IMPL:
            if self.tool_contract is None or self.agent_contract is not None or self.rag_contract is not None:
                raise ValueError("tool_impl artifacts require only tool_contract")
        return self


class ArtifactSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    display_name: str
    description: Optional[str] = None
    kind: ArtifactKind
    owner_type: ArtifactOwnerType
    type: ArtifactType
    version: str
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    runtime: ArtifactRuntimeConfig
    capabilities: ArtifactCapabilityConfig = Field(default_factory=ArtifactCapabilityConfig)
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None
    created_at: Optional[datetime] = None
    updated_at: datetime
    system_key: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ArtifactVersionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    artifact_id: str
    revision_number: int
    version_label: str
    is_published: bool = False
    is_current_draft: bool = False
    is_current_published: bool = False
    source_file_count: int = 0
    created_at: datetime
    created_by: Optional[str] = None


class ArtifactVersionSchema(ArtifactVersionListItem):
    display_name: str
    description: Optional[str] = None
    kind: ArtifactKind
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    runtime: ArtifactRuntimeConfig
    capabilities: ArtifactCapabilityConfig = Field(default_factory=ArtifactCapabilityConfig)
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None


class ArtifactWorkingDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: Optional[str] = None
    draft_key: Optional[str] = None
    draft_snapshot: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class ArtifactWorkingDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: Optional[str] = None
    draft_key: Optional[str] = None
    draft_snapshot: Dict[str, Any] = Field(default_factory=dict)


class ArtifactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str
    description: Optional[str] = None
    draft_key: Optional[str] = None
    kind: ArtifactKind
    runtime: ArtifactRuntimeConfig
    capabilities: ArtifactCapabilityConfig = Field(default_factory=ArtifactCapabilityConfig)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None

    @model_validator(mode="after")
    def validate_contracts(self) -> "ArtifactCreate":
        ArtifactContractEnvelope(
            kind=self.kind,
            agent_contract=self.agent_contract,
            rag_contract=self.rag_contract,
            tool_contract=self.tool_contract,
        )
        return self


class ArtifactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Optional[str] = None
    description: Optional[str] = None
    draft_key: Optional[str] = None
    runtime: Optional[ArtifactRuntimeConfig] = None
    capabilities: Optional[ArtifactCapabilityConfig] = None
    config_schema: Optional[Dict[str, Any]] = None
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None


class ArtifactConvertKindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ArtifactKind
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None

    @model_validator(mode="after")
    def validate_contracts(self) -> "ArtifactConvertKindRequest":
        ArtifactContractEnvelope(
            kind=self.kind,
            agent_contract=self.agent_contract,
            rag_contract=self.rag_contract,
            tool_contract=self.tool_contract,
        )
        return self


class ArtifactTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: Optional[str] = None
    source_files: list[ArtifactSourceFile] = Field(default_factory=list)
    entry_module_path: Optional[str] = None
    input_data: Any
    config: Dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    language: Optional[ArtifactLanguage] = None
    kind: Optional[ArtifactKind] = None
    runtime_target: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None


class ArtifactSourceValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: ArtifactLanguage
    source_files: list[ArtifactSourceFile] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class ArtifactSourceValidationDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    message: str
    line: int = 1
    column: int = 1
    end_line: int = 1
    end_column: int = 1
    severity: Literal["error"] = "error"
    code: Optional[str] = None


class ArtifactSourceValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnostics: list[ArtifactSourceValidationDiagnostic] = Field(default_factory=list)


class ArtifactDependencyAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: ArtifactLanguage
    source_files: list[ArtifactSourceFile] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class ArtifactDependencyRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    normalized_name: str
    declared_spec: Optional[str] = None
    classification: Literal["builtin", "runtime_provided", "declared"]
    source: Literal["builtin", "runtime_registry", "runtime_catalog", "declared"]
    status: str
    note: Optional[str] = None
    imported: bool = False
    declared: bool = False
    can_remove: bool = False
    can_add: bool = False
    needs_declaration: bool = False


class ArtifactDependencyAnalysisResponse(BaseModel):
    rows: list[ArtifactDependencyRow] = Field(default_factory=list)


class PythonPackageVerificationRequest(BaseModel):
    package_name: str


class PythonPackageVerificationResponse(BaseModel):
    package_name: str
    normalized_name: str
    status: Literal["exists", "not_found", "invalid", "lookup_failed"]
    exists: bool = False
    error_message: Optional[str] = None


class ArtifactTestResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    run_id: Optional[str] = None
    error_payload: Optional[Dict[str, Any]] = None
    stdout_excerpt: Optional[str] = None
    stderr_excerpt: Optional[str] = None


class ArtifactPublishResponse(BaseModel):
    artifact_id: str
    revision_id: str
    version: str
    status: Literal["published"] = "published"


class ArtifactTransferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str
    description: Optional[str] = None
    kind: ArtifactKind
    runtime: ArtifactRuntimeConfig
    capabilities: ArtifactCapabilityConfig = Field(default_factory=ArtifactCapabilityConfig)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    agent_contract: Optional[AgentArtifactContract] = None
    rag_contract: Optional[RAGArtifactContract] = None
    tool_contract: Optional[ToolArtifactContract] = None
    published: bool = False

    @model_validator(mode="after")
    def validate_contracts(self) -> "ArtifactTransferPayload":
        ArtifactContractEnvelope(
            kind=self.kind,
            agent_contract=self.agent_contract,
            rag_contract=self.rag_contract,
            tool_contract=self.tool_contract,
        )
        return self


class ArtifactTransferFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["talmudpedia.artifact"] = "talmudpedia.artifact"
    format_version: Literal[1] = 1
    exported_at: datetime
    artifact: ArtifactTransferPayload


class ArtifactImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact: ArtifactSchema
    source_published: bool = False


class ArtifactRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class ArtifactRunSchema(BaseModel):
    id: str
    artifact_id: Optional[str] = None
    revision_id: str
    domain: str
    status: ArtifactRunStatus
    queue_class: str
    result_payload: Optional[Dict[str, Any]] = None
    error_payload: Optional[Dict[str, Any]] = None
    stdout_excerpt: Optional[str] = None
    stderr_excerpt: Optional[str] = None
    duration_ms: Optional[int] = None
    runtime_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ArtifactRunCreateResponse(BaseModel):
    run_id: str
    status: ArtifactRunStatus


class ArtifactRuntimeQueueStatusSchema(BaseModel):
    queue_class: str
    active_count: int
    concurrency_limit: int


class ArtifactRunEventSchema(BaseModel):
    id: str
    sequence: int
    timestamp: Optional[datetime] = None
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
