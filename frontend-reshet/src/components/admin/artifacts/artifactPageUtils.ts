import {
  AgentArtifactContract,
  Artifact,
  ArtifactCapabilityConfig,
  ArtifactCreateRequest,
  ArtifactKind,
  ArtifactUpdateRequest,
  ArtifactVersion,
  RAGArtifactContract,
  ToolArtifactContract,
} from "@/services/artifacts";
import { ArtifactFormData, createFormDataForKind } from "@/components/admin/artifacts/artifactEditorState";

export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/__+/g, "_").replace(/^_|_$/g, "");
}

export function parseObjectJson(text: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text || "{}");
  } catch {
    throw new Error(`${label} must be valid JSON`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return parsed as Record<string, unknown>;
}

export function splitDependencies(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseCapabilities(text: string): ArtifactCapabilityConfig {
  return parseObjectJson(text, "Capabilities") as unknown as ArtifactCapabilityConfig;
}

export function parseAgentContract(text: string): AgentArtifactContract {
  return parseObjectJson(text, "Agent contract") as unknown as AgentArtifactContract;
}

export function parseRagContract(text: string): RAGArtifactContract {
  return parseObjectJson(text, "RAG contract") as unknown as RAGArtifactContract;
}

export function parseToolContract(text: string): ToolArtifactContract {
  return parseObjectJson(text, "Tool contract") as unknown as ToolArtifactContract;
}

export function tryParseObject(text: string, fallback: Record<string, unknown>): Record<string, unknown> {
  try {
    return parseObjectJson(text, "JSON");
  } catch {
    return fallback;
  }
}

export function formDataFromArtifact(artifact: Artifact): ArtifactFormData {
  const defaultAgentContract = JSON.parse(createFormDataForKind("agent_node").agent_contract) as Record<string, unknown>;
  const defaultRagContract = JSON.parse(createFormDataForKind("rag_operator").rag_contract) as Record<string, unknown>;
  const defaultToolContract = JSON.parse(createFormDataForKind("tool_impl").tool_contract) as Record<string, unknown>;
  const sourceFiles = artifact.runtime.source_files?.length
    ? artifact.runtime.source_files
    : createFormDataForKind(artifact.kind).source_files;

  return {
    slug: artifact.slug,
    display_name: artifact.display_name,
    description: artifact.description || "",
    kind: artifact.kind,
    source_files: sourceFiles,
    entry_module_path: artifact.runtime.entry_module_path || sourceFiles[0]?.path || "main.py",
    python_dependencies: (artifact.runtime.python_dependencies || []).join(", "),
    runtime_target: artifact.runtime.runtime_target || "cloudflare_workers",
    capabilities: JSON.stringify(artifact.capabilities || {}, null, 2),
    config_schema: JSON.stringify(artifact.config_schema || {}, null, 2),
    agent_contract: JSON.stringify(artifact.agent_contract || defaultAgentContract, null, 2),
    rag_contract: JSON.stringify(artifact.rag_contract || defaultRagContract, null, 2),
    tool_contract: JSON.stringify(artifact.tool_contract || defaultToolContract, null, 2),
  };
}

export function formDataFromArtifactVersion(version: ArtifactVersion): ArtifactFormData {
  const defaultAgentContract = JSON.parse(createFormDataForKind("agent_node").agent_contract) as Record<string, unknown>;
  const defaultRagContract = JSON.parse(createFormDataForKind("rag_operator").rag_contract) as Record<string, unknown>;
  const defaultToolContract = JSON.parse(createFormDataForKind("tool_impl").tool_contract) as Record<string, unknown>;
  const sourceFiles = version.runtime.source_files?.length
    ? version.runtime.source_files
    : createFormDataForKind(version.kind).source_files;

  return {
    slug: version.slug,
    display_name: version.display_name,
    description: version.description || "",
    kind: version.kind,
    source_files: sourceFiles,
    entry_module_path: version.runtime.entry_module_path || sourceFiles[0]?.path || "main.py",
    python_dependencies: (version.runtime.python_dependencies || []).join(", "),
    runtime_target: version.runtime.runtime_target || "cloudflare_workers",
    capabilities: JSON.stringify(version.capabilities || {}, null, 2),
    config_schema: JSON.stringify(version.config_schema || {}, null, 2),
    agent_contract: JSON.stringify(version.agent_contract || defaultAgentContract, null, 2),
    rag_contract: JSON.stringify(version.rag_contract || defaultRagContract, null, 2),
    tool_contract: JSON.stringify(version.tool_contract || defaultToolContract, null, 2),
  };
}

export function buildArtifactPayload(formData: ArtifactFormData): ArtifactCreateRequest {
  const payload: ArtifactCreateRequest = {
    slug: formData.slug,
    display_name: formData.display_name,
    description: formData.description || undefined,
    kind: formData.kind,
    runtime: {
      source_files: formData.source_files,
      entry_module_path: formData.entry_module_path,
      python_dependencies: splitDependencies(formData.python_dependencies),
      runtime_target: formData.runtime_target,
    },
    capabilities: parseCapabilities(formData.capabilities),
    config_schema: parseObjectJson(formData.config_schema, "Config schema"),
  };

  if (formData.kind === "agent_node") payload.agent_contract = parseAgentContract(formData.agent_contract);
  if (formData.kind === "rag_operator") payload.rag_contract = parseRagContract(formData.rag_contract);
  if (formData.kind === "tool_impl") payload.tool_contract = parseToolContract(formData.tool_contract);
  return payload;
}

export function buildArtifactUpdatePayload(formData: ArtifactFormData): ArtifactUpdateRequest {
  const payload: ArtifactUpdateRequest = {
    display_name: formData.display_name,
    description: formData.description || undefined,
    runtime: {
      source_files: formData.source_files,
      entry_module_path: formData.entry_module_path,
      python_dependencies: splitDependencies(formData.python_dependencies),
      runtime_target: formData.runtime_target,
    },
    capabilities: parseCapabilities(formData.capabilities),
    config_schema: parseObjectJson(formData.config_schema, "Config schema"),
  };

  if (formData.kind === "agent_node") payload.agent_contract = parseAgentContract(formData.agent_contract);
  if (formData.kind === "rag_operator") payload.rag_contract = parseRagContract(formData.rag_contract);
  if (formData.kind === "tool_impl") payload.tool_contract = parseToolContract(formData.tool_contract);
  return payload;
}

export function buildConvertPayload(targetKind: ArtifactKind, formData: ArtifactFormData) {
  if (targetKind === "agent_node") {
    return {
      kind: targetKind,
      agent_contract: parseAgentContract(formData.agent_contract),
    };
  }
  if (targetKind === "rag_operator") {
    return {
      kind: targetKind,
      rag_contract: parseRagContract(formData.rag_contract),
    };
  }
  return {
    kind: targetKind,
    tool_contract: parseToolContract(formData.tool_contract),
  };
}

export function kindLabel(kind: ArtifactKind): string {
  if (kind === "agent_node") return "Agent Node";
  if (kind === "rag_operator") return "RAG Operator";
  return "Tool Implementation";
}

export function contractEditorTitle(kind: ArtifactKind): string {
  if (kind === "agent_node") return "Agent Contract";
  if (kind === "rag_operator") return "RAG Contract";
  return "Tool Contract";
}

export function contractEditorDescription(kind: ArtifactKind): string {
  if (kind === "agent_node") return "State reads/writes, node UI, and typed graph IO.";
  if (kind === "rag_operator") return "Pipeline role, operator category, and typed pipeline IO.";
  return "Invocation schemas, side effects, and tool presentation metadata.";
}

export function serializeArtifactFormData(formData: ArtifactFormData): string {
  return JSON.stringify({
    ...formData,
    source_files: formData.source_files.map((file) => ({ path: file.path, content: file.content })),
  });
}
