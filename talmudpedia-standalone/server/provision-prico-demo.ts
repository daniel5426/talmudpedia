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
  tenantId: requireEnv("TALMUDPEDIA_TENANT_ID"),
  toolBaseUrl:
    String(process.env.PRICO_TOOL_BASE_URL || "").trim() ||
    `http://127.0.0.1:${Number(process.env.PORT || 3001)}/api/prico-tools`,
  modelId: String(process.env.PRICO_AGENT_MODEL_ID || "").trim(),
  adminToken: String(process.env.TALMUDPEDIA_ADMIN_BEARER_TOKEN || "").trim(),
  adminEmail: String(process.env.TALMUDPEDIA_ADMIN_EMAIL || "").trim(),
  adminPassword: String(process.env.TALMUDPEDIA_ADMIN_PASSWORD || "").trim(),
};

type TokenResponse = {
  access_token: string;
  token_type: string;
};

let resolvedAdminTokenPromise: Promise<string> | null = null;

async function resolveAdminToken(): Promise<string> {
  if (resolvedAdminTokenPromise) {
    return await resolvedAdminTokenPromise;
  }

  resolvedAdminTokenPromise = (async () => {
    if (env.adminToken) {
      return env.adminToken;
    }

    if (!env.adminEmail || !env.adminPassword) {
      throw new Error(
        "Missing admin auth. Set TALMUDPEDIA_ADMIN_BEARER_TOKEN or TALMUDPEDIA_ADMIN_EMAIL plus TALMUDPEDIA_ADMIN_PASSWORD.",
      );
    }

    const body = new URLSearchParams();
    body.set("username", env.adminEmail);
    body.set("password", env.adminPassword);

    const response = await fetch(`${env.baseUrl}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`POST /auth/login failed: ${response.status} ${text}`);
    }

    const payload = (await response.json()) as TokenResponse;
    const token = String(payload.access_token || "").trim();
    if (!token) {
      throw new Error("POST /auth/login succeeded but no access_token was returned.");
    }
    return token;
  })();

  return await resolvedAdminTokenPromise;
}

async function headers() {
  return {
    Authorization: `Bearer ${await resolveAdminToken()}`,
    "Content-Type": "application/json",
    "X-Tenant-ID": env.tenantId,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${env.baseUrl}${path}`, {
    ...init,
    headers: {
      ...(await headers()),
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
    headers: await headers(),
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
    {
      name: "PRICO Widget Output",
      slug: "prico-widget-output",
      description:
        "Render-only widget bundle contract for PRICO standalone chat responses. " +
        "Input must be strict JSON: { rows, optional screen_title, optional screen_subtitle }. " +
        "Each row is { widgets: [...] }. Allowed widgets: kpi, pie, bar, compare, table, note. " +
        "Use only the documented keys. Do not invent aliases or extra keys. " +
        "KPI = {kind,id,span,title,value}. " +
        "Pie/bar = {kind,id,span,title,data:[{label,value}]}. " +
        "Compare = {kind,id,span,title,leftLabel,leftValue,rightLabel,rightValue,optional delta}. " +
        "Table = {kind,id,span,title,columns,rows}. " +
        "Note = {kind,id,span,title,text}. " +
        "If the JSON bundle is invalid, this tool returns HTTP 400 with code INVALID_WIDGET_DSL and structured retry hints.",
      path: "/widget-output",
      input_schema: {
        type: "object",
        properties: {
          screen_title: { type: "string" },
          screen_subtitle: { type: "string" },
          rows: {
            type: "array",
            items: {
              type: "object",
              properties: {
                widgets: {
                  type: "array",
                  items: { type: "object", additionalProperties: true },
                },
              },
              required: ["widgets"],
              additionalProperties: false,
            },
          },
        },
        required: ["rows"],
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
    "Use the PRICO Widget Output tool only when visuals materially help comprehension.",
    "Do not use the PRICO Widget Output tool for purely explanatory answers.",
    "When you use the PRICO Widget Output tool, call it at most once per answer and bundle all widgets in that one call.",
    "If PRICO Widget Output fails with code INVALID_WIDGET_DSL, read the returned hint, fix the JSON, and retry exactly once.",
    "If the second PRICO Widget Output attempt fails, stop retrying and answer with text only.",
    "Keep normal assistant text as the primary answer even when you also produce widgets.",
    "For the widget tool, pass strict JSON only, never DSL, prose, or shorthand.",
    "Use only these widget kinds: kpi, pie, bar, compare, table, note.",
    "Use only these keys. Do not invent synonyms. Do not add extra keys.",
    "Bundle shape: { screen_title?: string, screen_subtitle?: string, rows: [{ widgets: Widget[] }] }.",
    "KPI shape: { kind: 'kpi', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, value: string }.",
    "Pie shape: { kind: 'pie', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, data: [{ label: string, value: number }] }.",
    "Bar shape: { kind: 'bar', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, data: [{ label: string, value: number }] }.",
    "Compare shape: { kind: 'compare', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, leftLabel: string, leftValue: number, rightLabel: string, rightValue: number, optional delta: string }.",
    "Table shape: { kind: 'table', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, columns: string[], rows: string[][] }.",
    "Note shape: { kind: 'note', id: string, span: number, title: string, optional subtitle: string, optional footnote: string, text: string }.",
    "Row span must be at most 12.",
    "Widget ids must be unique within the bundle.",
    "Table rows must have the same number of cells as columns.",
    "Use numeric values for chart and compare numbers, not strings.",
    "Canonical example widget payload:",
    '{"screen_title":"Client Activity","screen_subtitle":"Last 30 days","rows":[{"widgets":[{"kind":"kpi","id":"deals","span":3,"title":"Deals","value":"24"},{"kind":"kpi","id":"volume","span":3,"title":"Volume","value":"$12.4M"},{"kind":"kpi","id":"bank","span":3,"title":"Top Bank","value":"Hapoalim"},{"kind":"kpi","id":"currency","span":3,"title":"Top Currency","value":"USD"}]},{"widgets":[{"kind":"pie","id":"banks","span":6,"title":"Bank Concentration","data":[{"label":"Hapoalim","value":45},{"label":"Discount","value":30},{"label":"Leumi","value":25}]},{"kind":"table","id":"recent","span":6,"title":"Recent Deals","columns":["deal","date","bank"],"rows":[["1","2026-03-10","Hapoalim"],["2","2026-03-09","Discount"]]}]}]}.',
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
