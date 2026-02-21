import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { tool } from "@opencode-ai/plugin";

const CONTEXT_PATH = resolve(process.cwd(), ".cache/opencode/selected_agent_contract.json");

type UnknownRecord = Record<string, unknown>;

type ContractContext = {
  run_id?: string;
  app_id?: string;
  selected_agent_contract?: UnknownRecord;
};

function toInteger(value: unknown, defaultValue: number, min: number, max: number): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) return defaultValue;
  return Math.max(min, Math.min(max, parsed));
}

function summarizeSchema(schema: unknown, maxProperties: number): UnknownRecord {
  if (!schema || typeof schema !== "object") {
    return { type: "unknown", required: [], properties: [], property_count: 0 };
  }
  const payload = schema as UnknownRecord;
  const rawProperties = payload.properties;
  const properties = rawProperties && typeof rawProperties === "object" ? (rawProperties as UnknownRecord) : {};
  const entries = Object.entries(properties);

  const listed = entries.slice(0, maxProperties).map(([name, rawSpec]) => {
    const spec = rawSpec && typeof rawSpec === "object" ? (rawSpec as UnknownRecord) : {};
    const item: UnknownRecord = {
      name,
      type: String(spec.type || "unknown"),
    };
    const description = String(spec.description || "").trim();
    if (description) {
      item.description = description;
    }
    const enumValues = Array.isArray(spec.enum) ? spec.enum.slice(0, 8).map((value) => String(value)) : null;
    if (enumValues && enumValues.length > 0) {
      item.enum = enumValues;
    }
    return item;
  });

  const required = Array.isArray(payload.required) ? payload.required.slice(0, 40).map((item) => String(item)) : [];

  return {
    type: String(payload.type || "object"),
    required,
    properties: listed,
    property_count: entries.length,
    truncated_properties: entries.length > maxProperties,
  };
}

async function readContractContext(): Promise<ContractContext> {
  const raw = await readFile(CONTEXT_PATH, "utf8");
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object") {
    throw new Error("OpenCode contract context is invalid JSON.");
  }
  return parsed as ContractContext;
}

function assertContextMatches(args: { run_id: string; app_id?: string }, context: ContractContext): void {
  const contextRunId = String(context.run_id || "").trim();
  if (contextRunId && contextRunId !== args.run_id) {
    throw new Error(`Contract context run_id mismatch. expected=${args.run_id} actual=${contextRunId}`);
  }
  if (args.app_id) {
    const contextAppId = String(context.app_id || "").trim();
    if (contextAppId && contextAppId !== args.app_id) {
      throw new Error(`Contract context app_id mismatch. expected=${args.app_id} actual=${contextAppId}`);
    }
  }
}

export default tool({
  description:
    "Return a compact summary of the selected app-agent contract (tool readiness, schema fields, and optional x-ui hints).",
  args: {
    run_id: tool.schema.string().describe("Current coding-agent run id."),
    app_id: tool.schema.string().optional().describe("Optional app id for context validation."),
    max_tools: tool.schema.number().optional().describe("Maximum number of tools to include (1-50)."),
    max_properties_per_schema: tool.schema
      .number()
      .optional()
      .describe("Maximum schema properties to include per input/output schema (1-120)."),
    include_unresolved: tool.schema.boolean().optional().describe("Include unresolved tool references."),
  },
  async execute(args) {
    const context = await readContractContext();
    assertContextMatches(args, context);

    const contract = context.selected_agent_contract;
    if (!contract || typeof contract !== "object") {
      throw new Error("Contract context does not include selected_agent_contract.");
    }

    const payload = contract as UnknownRecord;
    const tools = Array.isArray(payload.tools) ? payload.tools : [];

    const maxTools = toInteger(args.max_tools, 12, 1, 50);
    const maxProps = toInteger(args.max_properties_per_schema, 20, 1, 120);
    const includeUnresolved = args.include_unresolved !== false;

    const summaries = tools.slice(0, maxTools).map((toolItem) => {
      const rawTool = toolItem && typeof toolItem === "object" ? (toolItem as UnknownRecord) : {};
      const runtimeReadiness =
        rawTool.runtime_readiness && typeof rawTool.runtime_readiness === "object"
          ? rawTool.runtime_readiness
          : { ready: false };

      return {
        id: String(rawTool.id || ""),
        slug: String(rawTool.slug || ""),
        name: String(rawTool.name || ""),
        description: rawTool.description ? String(rawTool.description) : null,
        runtime_readiness: runtimeReadiness,
        ui_hints: rawTool.ui_hints,
        input_schema: summarizeSchema(rawTool.input_schema, maxProps),
        output_schema: summarizeSchema(rawTool.output_schema, maxProps),
      };
    });

    const unresolved = Array.isArray(payload.unresolved_tool_references) ? payload.unresolved_tool_references : [];

    return {
      app_id: String(payload.app_id || ""),
      agent_id: String(payload.agent_id || ""),
      agent: payload.agent && typeof payload.agent === "object" ? payload.agent : {},
      ui_hint_standard:
        payload.ui_hint_standard && typeof payload.ui_hint_standard === "object" ? payload.ui_hint_standard : {},
      resolved_tool_count: Number(payload.resolved_tool_count || 0),
      returned_tool_count: summaries.length,
      truncated_tools: tools.length > maxTools,
      tools: summaries,
      unresolved_tool_references: includeUnresolved ? unresolved : [],
    };
  },
});
