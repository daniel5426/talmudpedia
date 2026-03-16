import { ArtifactKind, ArtifactSourceFile } from "@/services/artifacts";

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

export interface ArtifactFormData {
  display_name: string;
  description: string;
  kind: ArtifactKind;
  source_files: ArtifactSourceFile[];
  entry_module_path: string;
  python_dependencies: string;
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

export function createFormDataForKind(kind: ArtifactKind): ArtifactFormData {
  return {
    display_name: "",
    description: "",
    kind,
    source_files: [{ path: "main.py", content: DEFAULT_PYTHON_CODE }],
    entry_module_path: "main.py",
    python_dependencies: "",
    runtime_target: "cloudflare_workers",
    capabilities: JSON.stringify(defaultCapabilities, null, 2),
    config_schema: JSON.stringify({ type: "object", properties: {}, additionalProperties: true }, null, 2),
    agent_contract: JSON.stringify(defaultAgentContract, null, 2),
    rag_contract: JSON.stringify(defaultRagContract, null, 2),
    tool_contract: JSON.stringify(defaultToolContract, null, 2),
  };
}

export const initialFormData = createFormDataForKind("agent_node");
