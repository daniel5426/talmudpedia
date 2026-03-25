import { ArtifactKind, ArtifactLanguage, ArtifactSourceFile } from "@/services/artifacts";

export const ARTIFACT_KIND_OPTIONS: Array<{ value: ArtifactKind; label: string; description: string }> = [
  {
    value: "agent_node",
    label: "Agent Node",
    description: "Reads and writes agent state and participates in builder graphs.",
  },
  {
    value: "rag_operator",
    label: "RAG Operator",
    description: "Runs inside retrieval and ingestion pipelines with typed pipeline IO.",
  },
  {
    value: "tool_impl",
    label: "Tool Implementation",
    description: "Backs published tools with invocation schemas and explicit side effects.",
  },
];

export const RUNTIME_TARGET_OPTIONS = [
  { value: "cloudflare_workers", label: "Cloudflare Workers" },
];

export const DEFAULT_PYTHON_CODE = `async def execute(inputs, config, context):
    """
    Process artifact inputs and return a JSON-serializable result.
    """
    items = inputs.get("items") if isinstance(inputs, dict) else inputs
    return {
        "items": items,
        "config": config,
        "tenant_id": context.get("tenant_id"),
    }
`;

export const DEFAULT_JAVASCRIPT_CODE = `export async function execute(inputs, config, context) {
  const items = inputs?.items ?? inputs;
  return {
    items,
    config,
    tenant_id: context?.tenant_id ?? null,
  };
}
`;

export interface ArtifactFormData {
  display_name: string;
  description: string;
  kind: ArtifactKind;
  language: ArtifactLanguage;
  source_files: ArtifactSourceFile[];
  entry_module_path: string;
  dependencies: string;
  runtime_target: string;
  capabilities: string;
  config_schema: string;
  agent_contract: string;
  rag_contract: string;
  tool_contract: string;
}

const defaultCapabilities = {
  network_access: false,
  allowed_hosts: [],
  secret_refs: [],
  storage_access: [],
  side_effects: [],
};

const defaultAgentContract = {
  state_reads: [],
  state_writes: [],
  input_schema: {
    type: "object",
    properties: {
      items: { type: "array" },
    },
    additionalProperties: true,
  },
  output_schema: {
    type: "object",
    additionalProperties: true,
  },
  node_ui: {
    title: "Agent Node",
  },
};

const defaultRagContract = {
  operator_category: "transform",
  pipeline_role: "processor",
  input_schema: {
    type: "object",
    additionalProperties: true,
  },
  output_schema: {
    type: "object",
    additionalProperties: true,
  },
  execution_mode: "background",
};

const defaultToolContract = {
  input_schema: {
    type: "object",
    additionalProperties: true,
  },
  output_schema: {
    type: "object",
    additionalProperties: true,
  },
  side_effects: [],
  execution_mode: "interactive",
  tool_ui: {
    title: "Tool",
  },
};

export function createFormDataForKind(kind: ArtifactKind, language: ArtifactLanguage = "python"): ArtifactFormData {
  const isPython = language === "python";
  return {
    display_name: "",
    description: "",
    kind,
    language,
    source_files: [{ path: isPython ? "main.py" : "main.js", content: isPython ? DEFAULT_PYTHON_CODE : DEFAULT_JAVASCRIPT_CODE }],
    entry_module_path: isPython ? "main.py" : "main.js",
    dependencies: "",
    runtime_target: "cloudflare_workers",
    capabilities: JSON.stringify(defaultCapabilities, null, 2),
    config_schema: JSON.stringify({ type: "object", properties: {}, additionalProperties: true }, null, 2),
    agent_contract: JSON.stringify(defaultAgentContract, null, 2),
    rag_contract: JSON.stringify(defaultRagContract, null, 2),
    tool_contract: JSON.stringify(defaultToolContract, null, 2),
  };
}

export const initialFormData = createFormDataForKind("agent_node");
