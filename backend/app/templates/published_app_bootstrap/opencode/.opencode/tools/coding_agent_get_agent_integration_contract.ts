import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { tool } from "@opencode-ai/plugin";

const CONTEXT_PATH = resolve(process.cwd(), ".cache/opencode/selected_agent_contract.json");

type ContractContext = {
  run_id?: string;
  app_id?: string;
  selected_agent_contract?: Record<string, unknown>;
};

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
    "Return selected runtime-agent contract (resolved tools, schemas, and optional x-ui hints) for the current coding run.",
  args: {
    run_id: tool.schema.string().describe("Current coding-agent run id."),
    app_id: tool.schema.string().optional().describe("Optional app id for context validation."),
  },
  async execute(args) {
    const context = await readContractContext();
    assertContextMatches(args, context);
    const contract = context.selected_agent_contract;
    if (!contract || typeof contract !== "object") {
      throw new Error("Contract context does not include selected_agent_contract.");
    }
    return contract;
  },
});
