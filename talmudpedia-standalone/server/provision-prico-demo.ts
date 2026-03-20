import "dotenv/config";

type ModelRecord = {
  id: string;
  slug: string;
  name: string;
  is_default: boolean;
  is_active: boolean;
};

type ToolRecord = {
  id: string;
  slug: string;
  status: string;
};

type AgentRecord = {
  id: string;
  slug: string;
  status: string;
};

const requiredEnvKeys = [
  "TALMUDPEDIA_BASE_URL",
  "TALMUDPEDIA_ADMIN_BEARER_TOKEN",
  "TALMUDPEDIA_TENANT_ID",
] as const;

function requireEnv(key: (typeof requiredEnvKeys)[number]): string {
  const value = String(process.env[key] || "").trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function normalizeBaseUrl(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

const env = {
  baseUrl: normalizeBaseUrl(requireEnv("TALMUDPEDIA_BASE_URL")),
  adminToken: requireEnv("TALMUDPEDIA_ADMIN_BEARER_TOKEN"),
  tenantId: requireEnv("TALMUDPEDIA_TENANT_ID"),
  toolBaseUrl:
    String(process.env.PRICO_TOOL_BASE_URL || "").trim() ||
    `http://127.0.0.1:${Number(process.env.PORT || 3001)}/api/prico-tools`,
  modelId: String(process.env.PRICO_AGENT_MODEL_ID || "").trim(),
};

function headers() {
  return {
    Authorization: `Bearer ${env.adminToken}`,
    "Content-Type": "application/json",
    "X-Tenant-ID": env.tenantId,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${env.baseUrl}${path}`, {
    ...init,
    headers: {
      ...headers(),
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${init?.method || "GET"} ${path} failed: ${response.status} ${text}`);
  }

  return (await response.json()) as T;
}

async function maybePublish(path: string): Promise<void> {
  const response = await fetch(`${env.baseUrl}${path}`, {
    method: "POST",
    headers: headers(),
  });

  if (response.ok) {
    return;
  }

  const text = await response.text();
  throw new Error(`POST ${path} failed: ${response.status} ${text}`);
}

async function listTools(): Promise<ToolRecord[]> {
  const response = await request<{ tools: ToolRecord[]; total: number }>(
    "/tools?limit=200&skip=0",
  );
  return response.tools;
}

async function listAgents(): Promise<AgentRecord[]> {
  const response = await request<{ agents: AgentRecord[]; total: number }>(
    "/agents?limit=200&skip=0&compact=true",
  );
  return response.agents;
}

async function resolveModelId(): Promise<string> {
  if (env.modelId) {
    return env.modelId;
  }

  const response = await request<{ models: ModelRecord[]; total: number }>(
    "/models?limit=200&skip=0",
  );
  const preferredSlugs = [
    "gpt-4.1-mini",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1",
  ];
  const candidates = response.models.filter((model) => model.is_active);
  const preferred =
    candidates.find((model) => model.is_default) ||
    candidates.find((model) => preferredSlugs.includes(model.slug)) ||
    candidates[0];

  if (!preferred) {
    throw new Error(
      "No active chat model was found. Set PRICO_AGENT_MODEL_ID explicitly before provisioning.",
    );
  }

  return preferred.slug || preferred.id;
}

function toolDefinitions() {
  return [
    {
      name: "PRICO Client Activity Summary",
      slug: "prico-client-activity-summary",
      description: "Read-only summary of recent client activity in the PRICO demo domain.",
      path: "/client-activity-summary",
      input_schema: {
        type: "object",
        properties: {
          client_id: { type: "string" },
          date_from: { type: "string" },
          date_to: { type: "string" },
          currencies: {
            type: "array",
            items: { type: "string" },
          },
        },
        required: ["client_id"],
        additionalProperties: false,
      },
    },
    {
      name: "PRICO Bank Concentration",
      slug: "prico-bank-concentration",
      description: "Read-only concentration summary by bank for the PRICO demo domain.",
      path: "/bank-concentration",
      input_schema: {
        type: "object",
        properties: {
          client_id: { type: "string" },
          date_from: { type: "string" },
          date_to: { type: "string" },
        },
        required: ["client_id"],
        additionalProperties: false,
      },
    },
    {
      name: "PRICO Currency Concentration",
      slug: "prico-currency-concentration",
      description: "Read-only concentration summary by currency for the PRICO demo domain.",
      path: "/currency-concentration",
      input_schema: {
        type: "object",
        properties: {
          client_id: { type: "string" },
          date_from: { type: "string" },
          date_to: { type: "string" },
        },
        required: ["client_id"],
        additionalProperties: false,
      },
    },
    {
      name: "PRICO Deal Explainer",
      slug: "prico-deal-explainer",
      description: "Read-only detailed deal explainer for the PRICO demo domain.",
      path: "/deal-explainer",
      input_schema: {
        type: "object",
        properties: {
          client_id: { type: "string" },
          deal_id: { type: "string" },
        },
        required: ["client_id", "deal_id"],
        additionalProperties: false,
      },
    },
    {
      name: "PRICO Market Context",
      slug: "prico-market-context",
      description: "Read-only market benchmark comparison for a PRICO demo deal.",
      path: "/market-context",
      input_schema: {
        type: "object",
        properties: {
          client_id: { type: "string" },
          deal_id: { type: "string" },
        },
        required: ["client_id", "deal_id"],
        additionalProperties: false,
      },
    },
  ] as const;
}

async function upsertTool(definition: ReturnType<typeof toolDefinitions>[number]): Promise<ToolRecord> {
  const existing = (await listTools()).find((tool) => tool.slug === definition.slug);
  const payload = {
    name: definition.name,
    slug: definition.slug,
    description: definition.description,
    scope: "tenant",
    implementation_type: "HTTP",
    input_schema: definition.input_schema,
    output_schema: {
      type: "object",
      additionalProperties: true,
    },
    implementation_config: {
      type: "http",
      method: "POST",
      url: `${normalizeBaseUrl(env.toolBaseUrl)}${definition.path}`,
      headers: {
        "Content-Type": "application/json",
      },
      timeout_s: 20,
    },
    execution_config: {
      timeout_s: 20,
      is_pure: true,
      concurrency_group: "network",
      max_concurrency: 4,
    },
  };

  if (!existing) {
    const created = await request<ToolRecord>("/tools", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await maybePublish(`/tools/${created.id}/publish`);
    return created;
  }

  const updated = await request<ToolRecord>(`/tools/${existing.id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  if (String(existing.status || "").toLowerCase() !== "published") {
    await maybePublish(`/tools/${existing.id}/publish`);
  }
  return updated;
}

function buildAgentGraph(modelId: string, toolIds: string[]) {
  const instructions = [
    "You are the PRICO Client Exposure Copilot demo agent.",
    "You operate in read-only mode and support exactly one client at a time.",
    "Treat the selected client context as authoritative unless the user explicitly asks to switch clients.",
    "Use the available PRICO tools for factual claims. Do not invent exposure values, rates, benchmark deltas, or source rows.",
    "Keep the response compact unless the user explicitly asks for more detail.",
    "Prefer deal-specific tools when the user asks about a concrete deal id.",
    "Always surface evidence notes and any data-quality caveats returned by the tools.",
    "If the available demo data is partial or missing, say so clearly.",
  ].join(" ");

  return {
    spec_version: "1.0",
    nodes: [
      { id: "start", type: "start", position: { x: 0, y: 0 }, config: {} },
      {
        id: "prico_agent",
        type: "agent",
        position: { x: 260, y: 0 },
        config: {
          name: "PRICO Demo Agent",
          model_id: modelId,
          instructions,
          include_chat_history: true,
          output_format: "text",
          reasoning_effort: "medium",
          tools: toolIds,
          tool_execution_mode: "sequential",
          max_tool_iterations: 8,
          tool_timeout_s: 30,
        },
      },
      {
        id: "end",
        type: "end",
        position: { x: 520, y: 0 },
        config: { output_variable: "last_agent_output" },
      },
    ],
    edges: [
      { id: "e-start-agent", source: "start", target: "prico_agent", type: "control" },
      { id: "e-agent-end", source: "prico_agent", target: "end", type: "control" },
    ],
  };
}

async function upsertAgent(modelId: string, toolIds: string[]): Promise<AgentRecord> {
  const slug = "prico-demo-agent";
  const existing = (await listAgents()).find((agent) => agent.slug === slug);
  const payload = {
    name: "PRICO Demo Agent",
    slug,
    description: "Standalone PRICO demo agent backed by local HTTP tools.",
    graph_definition: buildAgentGraph(modelId, toolIds),
  };

  if (!existing) {
    return await request<AgentRecord>("/agents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  return await request<AgentRecord>(`/agents/${existing.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function validateAgent(agentId: string): Promise<void> {
  const result = await request<{ valid: boolean; errors: Array<Record<string, unknown>> }>(
    `/agents/${agentId}/validate`,
    { method: "POST" },
  );
  if (!result.valid) {
    throw new Error(`Agent validation failed: ${JSON.stringify(result.errors)}`);
  }
}

async function main() {
  console.log("Provisioning PRICO demo tools and agent...");
  const modelId = await resolveModelId();
  const tools = [];
  for (const definition of toolDefinitions()) {
    const tool = await upsertTool(definition);
    tools.push(tool);
    console.log(`Upserted tool: ${definition.slug} (${tool.id})`);
  }

  const agent = await upsertAgent(
    modelId,
    tools.map((tool) => tool.id),
  );
  await validateAgent(agent.id);
  await maybePublish(`/agents/${agent.id}/publish`);

  console.log("");
  console.log("Provisioning completed.");
  console.log(`Model: ${modelId}`);
  console.log(`Agent ID: ${agent.id}`);
  console.log("Tools:");
  for (const tool of tools) {
    console.log(`- ${tool.slug}: ${tool.id}`);
  }
  console.log("");
  console.log(
    "Set TALMUDPEDIA_AGENT_ID in talmudpedia-standalone/.env to the printed agent id before running the standalone demo.",
  );
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
