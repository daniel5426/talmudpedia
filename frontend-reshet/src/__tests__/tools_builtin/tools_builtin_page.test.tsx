import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import ToolsPage from "@/app/admin/tools/page"
import { agentService, toolsService } from "@/services"

jest.mock("@/services", () => ({
  toolsService: {
    listTools: jest.fn(),
    listBuiltinTemplates: jest.fn(),
    createBuiltinInstance: jest.fn(),
    deleteTool: jest.fn(),
    publishTool: jest.fn(),
  },
  agentService: {
    listOperators: jest.fn(),
  },
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/components/shared/RetrievalPipelineSelect", () => ({
  RetrievalPipelineSelect: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <input
      data-testid="retrieval-pipeline-select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
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
  status: "draft",
  version: "1.0.0",
  implementation_type: "http",
  published_at: null,
  tool_type: "custom",
  is_active: true,
  is_system: false,
  created_at: "2026-02-10T00:00:00Z",
  updated_at: "2026-02-10T00:00:00Z",
}

const retrievalTemplate = {
  id: "template-retrieval",
  tenant_id: null,
  name: "Retrieval Pipeline",
  slug: "builtin-retrieval-pipeline",
  description: "retrieve",
  scope: "global",
  input_schema: { type: "object", properties: {} },
  output_schema: { type: "object", properties: {} },
  config_schema: { implementation: { type: "rag_retrieval", pipeline_id: "" } },
  status: "published",
  version: "1.0.0",
  implementation_type: "rag_retrieval",
  published_at: "2026-02-10T00:00:00Z",
  tool_type: "built_in",
  builtin_key: "retrieval_pipeline",
  builtin_template_id: null,
  is_builtin_template: true,
  is_builtin_instance: false,
  is_active: true,
  is_system: true,
  created_at: "2026-02-10T00:00:00Z",
  updated_at: "2026-02-10T00:00:00Z",
}

describe("Tools built-in UI", () => {
  beforeEach(() => {
    ;(agentService.listOperators as jest.Mock).mockResolvedValue([])
    ;(toolsService.listTools as jest.Mock).mockResolvedValue({ tools: [baseTool], total: 1 })
    ;(toolsService.listBuiltinTemplates as jest.Mock).mockResolvedValue({
      tools: [retrievalTemplate],
      total: 1,
    })
    ;(toolsService.createBuiltinInstance as jest.Mock).mockResolvedValue({ ...baseTool, id: "instance-1" })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("renders built-in template browser", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listBuiltinTemplates).toHaveBeenCalled())

    expect(await screen.findByText("Built-in Templates")).toBeInTheDocument()
    expect(await screen.findByText("Retrieval Pipeline")).toBeInTheDocument()
  })

  it("creates retrieval built-in instance with selected pipeline", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listBuiltinTemplates).toHaveBeenCalled())

    fireEvent.click(screen.getByRole("button", { name: "Create Built-in Instance" }))

    const pipelineInput = await screen.findByTestId("retrieval-pipeline-select")
    fireEvent.change(pipelineInput, { target: { value: "pipeline-123" } })

    fireEvent.click(screen.getByRole("button", { name: "Create Instance" }))

    await waitFor(() => {
      expect(toolsService.createBuiltinInstance).toHaveBeenCalledWith(
        "retrieval_pipeline",
        expect.objectContaining({
          implementation_config: expect.objectContaining({ pipeline_id: "pipeline-123" }),
        })
      )
    })
  })
})
