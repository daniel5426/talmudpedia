import { getNodeUiDefaults } from "@/components/agent-builder/types"
import { nodeTypes } from "@/components/agent-builder/nodes"

describe("agent builder nodeTypes registry", () => {
  it("resolves any runtime node type to the shared BaseNode renderer", () => {
    expect(nodeTypes.agent).toBeDefined()
    expect(nodeTypes.start).toBeDefined()
    expect(nodeTypes["artifact:test"]).toBeDefined()
    expect(nodeTypes["custom-runtime-type"]).toBeDefined()
  })

  it("removes legacy built-in node defaults from the authoring surface", () => {
    expect(getNodeUiDefaults("conditional")).toBeUndefined()
    expect(getNodeUiDefaults("human_input")).toBeUndefined()
  })
})
