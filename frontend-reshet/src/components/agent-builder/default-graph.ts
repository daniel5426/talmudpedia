import type { AgentGraphDefinition } from "@/services/agent"

import { buildDefaultEndOutputBindings, buildDefaultEndOutputSchema } from "./graph-contract"

export function buildDefaultAgentGraph(): AgentGraphDefinition {
  return {
    spec_version: "4.0",
    nodes: [
      {
        id: "start",
        type: "start",
        position: { x: 0, y: 0 },
        config: {},
      },
      {
        id: "agent",
        type: "agent",
        position: { x: 240, y: 0 },
        config: {},
      },
      {
        id: "end",
        type: "end",
        position: { x: 480, y: 0 },
        config: {
          output_schema: buildDefaultEndOutputSchema(),
          output_bindings: buildDefaultEndOutputBindings(),
        },
      },
    ],
    edges: [
      {
        id: "e_start_agent",
        source: "start",
        target: "agent",
        type: "control",
      },
      {
        id: "e_agent_end",
        source: "agent",
        target: "end",
        type: "control",
      },
    ],
  }
}
