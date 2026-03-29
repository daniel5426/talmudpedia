import {
  AgentArtifactContract,
  Artifact,
  ArtifactLanguage,
  ArtifactCapabilityConfig,
  ArtifactCreateRequest,
  ArtifactKind,
  ArtifactUpdateRequest,
  ArtifactVersion,
  RAGArtifactContract,
  ToolArtifactContract,
} from "@/services/artifacts";
import { ArtifactFormData, createFormDataForKind } from "@/components/admin/artifacts/artifactEditorState";
import { canonicalizeCredentialMentions } from "@/lib/credential-mentions";

type ArtifactConfigClipboardSnapshot = Pick<
  ArtifactFormData,
  | "display_name"
  | "description"
  | "entry_module_path"
  | "dependencies"
  | "runtime_target"
  | "capabilities"
  | "config_schema"
  | "agent_contract"
  | "rag_contract"
  | "tool_contract"
>;

type ArtifactConfigClipboardEnvelope = {
  type: "talmudpedia.artifact-config";
  version: 1;
  kind: ArtifactKind;
  language: ArtifactLanguage;
  config: ArtifactConfigClipboardSnapshot;
};

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
  const parsed = parseObjectJson(text, "Tool contract");
  if (isRecord(parsed.tool_contract)) {
    throw new Error("Tool contract must be the inner contract object, not wrapped in an outer 'tool_contract' field");
  }
  if (!isRecord(parsed.input_schema)) {
    throw new Error("Tool contract.input_schema must be a JSON object");
  }
  if (!isRecord(parsed.output_schema)) {
    throw new Error("Tool contract.output_schema must be a JSON object");
  }
  return parsed as unknown as ToolArtifactContract;
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
    display_name: artifact.display_name,
    description: artifact.description || "",
    kind: artifact.kind,
    language: artifact.runtime.language || "python",
    source_files: sourceFiles,
    entry_module_path: artifact.runtime.entry_module_path || sourceFiles[0]?.path || "main.py",
    dependencies: (artifact.runtime.dependencies || []).join(", "),
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
    display_name: version.display_name,
    description: version.description || "",
    kind: version.kind,
    language: version.runtime.language || "python",
    source_files: sourceFiles,
    entry_module_path: version.runtime.entry_module_path || sourceFiles[0]?.path || "main.py",
    dependencies: (version.runtime.dependencies || []).join(", "),
    runtime_target: version.runtime.runtime_target || "cloudflare_workers",
    capabilities: JSON.stringify(version.capabilities || {}, null, 2),
    config_schema: JSON.stringify(version.config_schema || {}, null, 2),
    agent_contract: JSON.stringify(version.agent_contract || defaultAgentContract, null, 2),
    rag_contract: JSON.stringify(version.rag_contract || defaultRagContract, null, 2),
    tool_contract: JSON.stringify(version.tool_contract || defaultToolContract, null, 2),
  };
}

export function formDataFromDraftSnapshot(
  artifact: Pick<Artifact, "display_name" | "description" | "kind">,
  snapshot: Record<string, unknown>,
): ArtifactFormData {
  const defaultAgentContract = JSON.parse(createFormDataForKind("agent_node").agent_contract) as Record<string, unknown>;
  const defaultRagContract = JSON.parse(createFormDataForKind("rag_operator").rag_contract) as Record<string, unknown>;
  const defaultToolContract = JSON.parse(createFormDataForKind("tool_impl").tool_contract) as Record<string, unknown>;
  const kind = (typeof snapshot.kind === "string" ? snapshot.kind : artifact.kind) as ArtifactKind;
  const sourceFiles = Array.isArray(snapshot.source_files)
    ? snapshot.source_files as ArtifactFormData["source_files"]
    : createFormDataForKind(kind).source_files;

  return {
    display_name: typeof snapshot.display_name === "string" ? snapshot.display_name : artifact.display_name,
    description: typeof snapshot.description === "string" ? snapshot.description : (artifact.description || ""),
    kind,
    language: typeof snapshot.language === "string" ? snapshot.language as ArtifactFormData["language"] : "python",
    source_files: sourceFiles,
    entry_module_path: typeof snapshot.entry_module_path === "string" ? snapshot.entry_module_path : sourceFiles[0]?.path || "main.py",
    dependencies: typeof snapshot.dependencies === "string" ? snapshot.dependencies : (typeof snapshot.python_dependencies === "string" ? snapshot.python_dependencies : ""),
    runtime_target: typeof snapshot.runtime_target === "string" ? snapshot.runtime_target : "cloudflare_workers",
    capabilities: typeof snapshot.capabilities === "string" ? snapshot.capabilities : JSON.stringify({}, null, 2),
    config_schema: typeof snapshot.config_schema === "string" ? snapshot.config_schema : JSON.stringify({}, null, 2),
    agent_contract: typeof snapshot.agent_contract === "string" ? snapshot.agent_contract : JSON.stringify(defaultAgentContract, null, 2),
    rag_contract: typeof snapshot.rag_contract === "string" ? snapshot.rag_contract : JSON.stringify(defaultRagContract, null, 2),
    tool_contract: typeof snapshot.tool_contract === "string" ? snapshot.tool_contract : JSON.stringify(defaultToolContract, null, 2),
  };
}

export function buildArtifactPayload(formData: ArtifactFormData, draftKey?: string | null): ArtifactCreateRequest {
  const payload: ArtifactCreateRequest = {
    display_name: formData.display_name,
    description: formData.description || undefined,
    draft_key: draftKey || undefined,
    kind: formData.kind,
    runtime: {
      language: formData.language,
      source_files: formData.source_files.map((file) => ({
        ...file,
        content: canonicalizeCredentialMentions(file.content),
      })),
      entry_module_path: formData.entry_module_path,
      dependencies: splitDependencies(formData.dependencies),
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

export function buildArtifactUpdatePayload(formData: ArtifactFormData, draftKey?: string | null): ArtifactUpdateRequest {
  const payload: ArtifactUpdateRequest = {
    display_name: formData.display_name,
    description: formData.description || undefined,
    draft_key: draftKey || undefined,
    runtime: {
      language: formData.language,
      source_files: formData.source_files.map((file) => ({
        ...file,
        content: canonicalizeCredentialMentions(file.content),
      })),
      entry_module_path: formData.entry_module_path,
      dependencies: splitDependencies(formData.dependencies),
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
  const normalizeJsonText = (text: string): unknown => {
    try {
      return sortJsonValue(JSON.parse(text));
    } catch {
      return text;
    }
  };

  return JSON.stringify({
    ...formData,
    dependencies: splitDependencies(formData.dependencies).join(", "),
    capabilities: normalizeJsonText(formData.capabilities),
    config_schema: normalizeJsonText(formData.config_schema),
    agent_contract: normalizeJsonText(formData.agent_contract),
    rag_contract: normalizeJsonText(formData.rag_contract),
    tool_contract: normalizeJsonText(formData.tool_contract),
    source_files: formData.source_files.map((file) => ({ path: file.path, content: file.content })),
  });
}

export function buildArtifactConfigClipboardText(formData: ArtifactFormData): string {
  const payload: ArtifactConfigClipboardEnvelope = {
    type: "talmudpedia.artifact-config",
    version: 1,
    kind: formData.kind,
    language: formData.language,
    config: {
      display_name: formData.display_name,
      description: formData.description,
      entry_module_path: formData.entry_module_path,
      dependencies: formData.dependencies,
      runtime_target: formData.runtime_target,
      capabilities: formData.capabilities,
      config_schema: formData.config_schema,
      agent_contract: formData.agent_contract,
      rag_contract: formData.rag_contract,
      tool_contract: formData.tool_contract,
    },
  };

  return JSON.stringify(payload, null, 2);
}

export function parseArtifactConfigClipboardText(
  text: string,
  currentFormData: Pick<ArtifactFormData, "kind" | "language" | "source_files">,
): ArtifactConfigClipboardSnapshot {
  const parsed = parseObjectJson(text, "Copied configuration");

  if (parsed.type !== "talmudpedia.artifact-config" || parsed.version !== 1) {
    throw new Error("Clipboard does not contain a copied artifact configuration");
  }
  if (parsed.kind !== currentFormData.kind) {
    throw new Error("Copied configuration kind does not match this artifact");
  }
  if (parsed.language !== currentFormData.language) {
    throw new Error("Copied configuration language does not match this artifact");
  }
  if (!isRecord(parsed.config)) {
    throw new Error("Copied configuration is missing its config payload");
  }

  const config = parsed.config;
  const nextSnapshot: ArtifactConfigClipboardSnapshot = {
    display_name: typeof config.display_name === "string" ? config.display_name : "",
    description: typeof config.description === "string" ? config.description : "",
    entry_module_path: typeof config.entry_module_path === "string" ? config.entry_module_path : "",
    dependencies: typeof config.dependencies === "string" ? config.dependencies : "",
    runtime_target: typeof config.runtime_target === "string" ? config.runtime_target : "cloudflare_workers",
    capabilities: typeof config.capabilities === "string" ? config.capabilities : JSON.stringify({}, null, 2),
    config_schema: typeof config.config_schema === "string" ? config.config_schema : JSON.stringify({}, null, 2),
    agent_contract: typeof config.agent_contract === "string" ? config.agent_contract : JSON.stringify({}, null, 2),
    rag_contract: typeof config.rag_contract === "string" ? config.rag_contract : JSON.stringify({}, null, 2),
    tool_contract: typeof config.tool_contract === "string" ? config.tool_contract : JSON.stringify({}, null, 2),
  };

  if (!currentFormData.source_files.some((file) => file.path === nextSnapshot.entry_module_path)) {
    throw new Error("Copied entry module path does not exist in this artifact's files");
  }

  return nextSnapshot;
}

function isPythonPath(path: string): boolean {
  return String(path || "").trim().toLowerCase().endsWith(".py");
}

function isJavascriptPath(path: string): boolean {
  const normalized = String(path || "").trim().toLowerCase();
  return normalized.endsWith(".js") || normalized.endsWith(".mjs") || normalized.endsWith(".ts") || normalized.endsWith(".mts");
}

export function getArtifactLanguageWarningPaths(
  language: ArtifactLanguage,
  sourceFiles: Array<{ path: string }>,
): string[] {
  return Array.from(new Set(
    sourceFiles
      .map((file) => String(file.path || "").trim())
      .filter((path) => path && (language === "python" ? isJavascriptPath(path) : isPythonPath(path))),
  )).sort();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sortJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sortJsonValue(item));
  }
  if (isRecord(value)) {
    return Object.keys(value)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortJsonValue(value[key]);
        return acc;
      }, {});
  }
  return value;
}
