import { Node } from "@xyflow/react"

import { normalizeBuilderNode, normalizeGraphSpecForSave, resolveGraphSpecVersion } from "@/components/agent-builder/graphspec"
import { AgentNodeData } from "@/components/agent-builder/types"

const buildNode = (id: string, type: string, config: Record<string, unknown> = {}): Node<AgentNodeData> => ({
  id,
  type,
  position: { x: 0, y: 0 },
  config,
  data: {
    nodeType: type as any,
    category: type === "start" || type === "end" ? "control" : "reasoning",
    displayName: type,
    config,
    inputType: "any",
    outputType: "any",
    isConfigured: true,
    hasErrors: false,
  },
} as Node<AgentNodeData>)

describe("graphspec v3 serialization", () => {
  it("always persists spec version 3.0", () => {
    const nodes = [buildNode("start", "start"), buildNode("agent", "agent", { model_id: "model-1" })]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" })

    expect(saved.spec_version).toBe("3.0")
    expect(resolveGraphSpecVersion(nodes, "2.0")).toBe("3.0")
  })

  it("hydrates default end schema config when legacy end config is empty", () => {
    const normalized = normalizeBuilderNode(buildNode("end", "end", {}))
    const config = normalized.data.config as Record<string, unknown>

    expect(config.output_schema).toBeDefined()
    expect(Array.isArray(config.output_bindings)).toBe(true)
  })
})
