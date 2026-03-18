import { filterTools, getToolBucket } from "@/lib/tool-types"

const now = "2026-02-10T00:00:00Z"

const tools = [
  {
    id: "builtin-1",
    tenant_id: "tenant-1",
    name: "Builtin Retrieval",
    slug: "builtin-retrieval",
    description: "built in",
    input_schema: {},
    output_schema: {},
    config_schema: {},
    implementation_type: "custom",
    implementation_config: {},
    execution_config: {},
    version: "1.0.0",
    status: "published",
    ownership: "system",
    managed_by: "system",
    can_edit_in_registry: false,
    can_publish_in_registry: false,
    can_delete_in_registry: false,
    created_at: now,
    updated_at: now,
    published_at: now,
    builtin_key: "retrieval_pipeline",
    is_builtin_template: false,
    is_builtin_instance: true,
  },
  {
    id: "mcp-1",
    tenant_id: "tenant-1",
    name: "MCP Tool",
    slug: "mcp-tool",
    description: "mcp",
    input_schema: {},
    output_schema: {},
    config_schema: {},
    implementation_type: "mcp",
    implementation_config: {},
    execution_config: {},
    version: "1.0.0",
    status: "published",
    ownership: "manual",
    managed_by: "tools",
    can_edit_in_registry: true,
    can_publish_in_registry: true,
    can_delete_in_registry: true,
    created_at: now,
    updated_at: now,
    published_at: now,
  },
  {
    id: "custom-1",
    tenant_id: "tenant-1",
    name: "Custom Tool",
    slug: "custom-tool",
    description: "custom",
    input_schema: {},
    output_schema: {},
    config_schema: {},
    implementation_type: "http",
    implementation_config: {},
    execution_config: {},
    version: "1.0.0",
    status: "draft",
    ownership: "manual",
    managed_by: "tools",
    can_edit_in_registry: true,
    can_publish_in_registry: true,
    can_delete_in_registry: true,
    created_at: now,
    updated_at: now,
    published_at: null,
  },
] as any

describe("tool bucket filtering", () => {
  it("classifies built-in bucket via builtin metadata", () => {
    expect(getToolBucket(tools[0])).toBe("built_in")
    expect(getToolBucket(tools[1])).toBe("mcp")
    expect(getToolBucket(tools[2])).toBe("custom")
  })

  it("filters by bucket and subtype coherently", () => {
    const builtIns = filterTools(tools, { bucket: "built_in", status: "all", subtype: "all", query: "" })
    expect(builtIns).toHaveLength(1)
    expect(builtIns[0].id).toBe("builtin-1")

    const mcp = filterTools(tools, { bucket: "mcp", status: "all", subtype: "all", query: "" })
    expect(mcp).toHaveLength(1)
    expect(mcp[0].id).toBe("mcp-1")

    const httpSubtype = filterTools(tools, { bucket: "all", status: "all", subtype: "http", query: "" })
    expect(httpSubtype).toHaveLength(1)
    expect(httpSubtype[0].id).toBe("custom-1")
  })
})
