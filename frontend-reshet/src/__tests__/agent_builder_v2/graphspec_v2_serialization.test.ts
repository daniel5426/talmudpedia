import { Node } from "@xyflow/react"

import { normalizeGraphSpecForSave, resolveGraphSpecVersion } from "@/components/agent-builder/graphspec"
import { AgentNodeData } from "@/components/agent-builder/types"

const buildNode = (id: string, type: string, config: Record<string, unknown> = {}): Node<AgentNodeData> => ({
  id,
  type,
  position: { x: 0, y: 0 },
  data: {
    nodeType: type as any,
    category: "logic",
    displayName: type,
    config,
    inputType: "any",
    outputType: "any",
    isConfigured: true,
    hasErrors: false,
  },
})

describe("graphspec v2 serialization", () => {
  it("preserves loaded spec version when there are no v2 orchestration nodes", () => {
    const nodes = [buildNode("n1", "start"), buildNode("n2", "agent")]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "2.0" })
    expect(saved.spec_version).toBe("2.0")
  })

  it("forces v2 when orchestration nodes exist", () => {
    const nodes = [buildNode("n1", "start"), buildNode("n2", "spawn_group")]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" })
    expect(saved.spec_version).toBe("2.0")
  })

  it("never downgrades v2 orchestration graphs to v1", () => {
    const nodes = [buildNode("n1", "join"), buildNode("n2", "judge")]
    expect(resolveGraphSpecVersion(nodes, "1.0")).toBe("2.0")
    expect(normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" }).spec_version).toBe("2.0")
  })

  it("autogenerates idempotency defaults for orchestration spawn nodes", () => {
    const nodes = [
      buildNode("spawn-run-node", "spawn_run", {
        target_agent_slug: "planner-agent",
        scope_subset: ["agents.read"],
      }),
      buildNode("spawn-group-node", "spawn_group", {
        targets: [{ target_agent_slug: "planner-agent" }],
        scope_subset: ["agents.read"],
      }),
    ]

    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "2.0" })
    const spawnRunConfig = (saved.nodes[0].data as AgentNodeData).config as Record<string, unknown>
    const spawnGroupConfig = (saved.nodes[1].data as AgentNodeData).config as Record<string, unknown>

    expect(typeof spawnRunConfig.idempotency_key).toBe("string")
    expect(String(spawnRunConfig.idempotency_key)).toContain("spawn-run-node:")
    expect(typeof spawnGroupConfig.idempotency_key_prefix).toBe("string")
    expect(String(spawnGroupConfig.idempotency_key_prefix)).toContain("spawn-group-node:")
  })

  it("normalizes route_table inputs for router and judge configs", () => {
    const nodes = [
      buildNode("router-node", "router", {
        route_table: [{ name: "replan", match: "replan" }, { name: "continue", match: "continue" }],
      }),
      buildNode("judge-node", "judge", {
        route_table: [{ name: "accept" }, { name: "reject" }],
      }),
    ]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "2.0" })
    const routerConfig = (saved.nodes[0].data as AgentNodeData).config as Record<string, unknown>
    const judgeConfig = (saved.nodes[1].data as AgentNodeData).config as Record<string, unknown>

    expect(Array.isArray(routerConfig.routes)).toBe(true)
    expect(routerConfig.routes).toEqual([
      { name: "replan", match: "replan" },
      { name: "continue", match: "continue" },
    ])
    expect(judgeConfig.outcomes).toEqual(["accept", "reject"])
  })
})
