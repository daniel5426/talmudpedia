import { getToolBucket, getSubtypeLabel, filterTools } from "@/lib/tool-types"
import { ToolDefinition } from "@/services/agent"

const baseTool = (overrides: Partial<ToolDefinition>): ToolDefinition => ({
  id: "tool-1",
  name: "Alpha",
  slug: "alpha",
  description: "Alpha tool",
  input_schema: {},
  output_schema: {},
  implementation_type: "http",
  implementation_config: {},
  execution_config: {},
  version: "1.0.0",
  status: "draft",
  tenant_id: "tenant-1",
  created_at: "",
  updated_at: "",
  published_at: null,
  ...overrides,
})

test("getToolBucket derives bucket from fields", () => {
  const artifactTool = baseTool({ implementation_type: "artifact", artifact_id: "custom/tool" })
  const mcpTool = baseTool({ implementation_type: "mcp" })
  const internalTool = baseTool({ implementation_type: "internal" })
  const customTool = baseTool({ implementation_type: "http" })

  expect(getToolBucket(artifactTool)).toBe("artifact")
  expect(getToolBucket(mcpTool)).toBe("mcp")
  expect(getToolBucket(internalTool)).toBe("built_in")
  expect(getToolBucket(customTool)).toBe("custom")
})

test("getSubtypeLabel returns readable label", () => {
  expect(getSubtypeLabel("rag_retrieval")).toBe("RAG Retrieval")
})

test("filterTools supports query and subtype filtering", () => {
  const tools = [
    baseTool({ id: "1", name: "Alpha", slug: "alpha", implementation_type: "http" }),
    baseTool({ id: "2", name: "Beta", slug: "beta", implementation_type: "artifact", artifact_id: "custom/tool" }),
  ]

  const filtered = filterTools(tools, { query: "beta", subtype: "artifact", bucket: "all", status: "all" })
  expect(filtered).toHaveLength(1)
  expect(filtered[0].slug).toBe("beta")
})
