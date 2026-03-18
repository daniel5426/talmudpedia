import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import ToolsPage from "@/app/admin/tools/page"
import { toolsService } from "@/services"

const push = jest.fn()

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}))

jest.mock("@/services", () => ({
  toolsService: {
    listTools: jest.fn(),
    createTool: jest.fn(),
    deleteTool: jest.fn(),
    publishTool: jest.fn(),
  },
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

const baseTool = {
  id: "tool-1",
  tenant_id: "tenant-1",
  name: "HTTP Tool",
  slug: "http-tool",
  description: "http",
  scope: "tenant",
  input_schema: { type: "object", properties: {} },
  output_schema: { type: "object", properties: {} },
  config_schema: { implementation: { type: "http", method: "GET", url: "https://example.com" } },
  implementation_config: { type: "http", method: "GET", url: "https://example.com" },
  execution_config: {},
  status: "draft",
  version: "1.0.0",
  implementation_type: "http",
  published_at: null,
  tool_type: "custom",
  ownership: "manual",
  managed_by: "tools",
  source_object_type: null,
  source_object_id: null,
  can_edit_in_registry: true,
  can_publish_in_registry: true,
  can_delete_in_registry: true,
  is_active: true,
  is_system: false,
  created_at: "2026-02-10T00:00:00Z",
  updated_at: "2026-02-10T00:00:00Z",
}

const retrievalBuiltin = {
  id: "template-retrieval",
  tenant_id: null,
  name: "Retrieval Pipeline",
  slug: "builtin-retrieval-pipeline",
  description: "retrieve",
  scope: "global",
  input_schema: { type: "object", properties: {} },
  output_schema: { type: "object", properties: {} },
  config_schema: { implementation: { type: "rag_pipeline", pipeline_id: "" } },
  implementation_config: { type: "rag_pipeline", pipeline_id: "" },
  execution_config: {},
  status: "published",
  version: "1.0.0",
  implementation_type: "rag_pipeline",
  published_at: "2026-02-10T00:00:00Z",
  tool_type: "built_in",
  ownership: "system",
  managed_by: "system",
  source_object_type: null,
  source_object_id: null,
  can_edit_in_registry: false,
  can_publish_in_registry: false,
  can_delete_in_registry: false,
  builtin_key: "retrieval_pipeline",
  builtin_template_id: null,
  is_builtin_template: false,
  is_builtin_instance: false,
  is_active: true,
  is_system: true,
  created_at: "2026-02-10T00:00:00Z",
  updated_at: "2026-02-10T00:00:00Z",
}

const artifactTool = {
  ...baseTool,
  id: "artifact-tool-1",
  name: "Artifact Owned Tool",
  slug: "artifact-owned-tool",
  implementation_type: "artifact",
  artifact_id: "artifact-123",
  ownership: "artifact_bound",
  managed_by: "artifacts",
  source_object_type: "artifact",
  source_object_id: "artifact-123",
  can_edit_in_registry: false,
  can_publish_in_registry: false,
  can_delete_in_registry: false,
}

const pipelineTool = {
  ...baseTool,
  id: "pipeline-tool-1",
  name: "Pipeline Owned Tool",
  slug: "pipeline-owned-tool",
  implementation_type: "rag_pipeline",
  visual_pipeline_id: "pipeline-123",
  ownership: "pipeline_bound",
  managed_by: "pipelines",
  source_object_type: "pipeline",
  source_object_id: "pipeline-123",
  can_edit_in_registry: false,
  can_publish_in_registry: false,
  can_delete_in_registry: false,
}

describe("Tools built-in UI", () => {
  beforeEach(() => {
    push.mockReset()
    ;(toolsService.listTools as jest.Mock).mockResolvedValue({ tools: [baseTool, retrievalBuiltin, artifactTool, pipelineTool], total: 4 })
    ;(toolsService.createTool as jest.Mock).mockResolvedValue({ ...baseTool, id: "tool-created-1" })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("renders built-in tools from the main tools list", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    expect(await screen.findByText("Retrieval Pipeline")).toBeInTheDocument()
  })

  it("removes create built-in instance action from tools page", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    expect(screen.queryByRole("button", { name: "Create Built-in Instance" })).not.toBeInTheDocument()
  })

  it("opens artifact editor from the tool detail sheet", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    fireEvent.click(await screen.findByText("Artifact Owned Tool"))
    expect(screen.getByText("Artifacts")).toBeInTheDocument()
    fireEvent.click(await screen.findByRole("button", { name: "Open Editor" }))

    expect(push).toHaveBeenCalledWith("/admin/artifacts?mode=edit&id=artifact-123")
  })

  it("opens pipeline editor from the tool detail sheet", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    fireEvent.click(await screen.findByText("Pipeline Owned Tool"))
    fireEvent.click(await screen.findByRole("button", { name: "Open Editor" }))

    expect(push).toHaveBeenCalledWith("/admin/pipelines/pipeline-123?toolSettings=1")
  })
})
