import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import ToolsPage from "@/app/admin/tools/page"
import { agentService, toolsService } from "@/services"

jest.mock("@/services", () => ({
  toolsService: {
    listTools: jest.fn(),
    createTool: jest.fn(),
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

const retrievalBuiltin = {
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
  is_builtin_template: false,
  is_builtin_instance: false,
  is_active: true,
  is_system: true,
  created_at: "2026-02-10T00:00:00Z",
  updated_at: "2026-02-10T00:00:00Z",
}

describe("Tools built-in UI", () => {
  beforeEach(() => {
    ;(agentService.listOperators as jest.Mock).mockResolvedValue([])
    ;(toolsService.listTools as jest.Mock).mockResolvedValue({ tools: [baseTool, retrievalBuiltin], total: 2 })
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

  it.skip("creates rag_retrieval tool with selected retrieval pipeline", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "New Tool" }))
    fireEvent.change(screen.getByPlaceholderText("Web Search"), { target: { value: "RAG Tool" } })
    fireEvent.change(screen.getByPlaceholderText("web-search"), { target: { value: "rag-tool" } })
    fireEvent.change(
      screen.getByPlaceholderText("Search the web for current information..."),
      { target: { value: "retrieval tool" } }
    )

    const comboboxes = screen.getAllByRole("combobox")
    const implementationSelect = comboboxes[comboboxes.length - 1]
    fireEvent.mouseDown(implementationSelect)
    fireEvent.click(await screen.findByText("RAG Retrieval"))

    const pipelineInput = await screen.findByTestId("retrieval-pipeline-select")
    fireEvent.change(pipelineInput, { target: { value: "pipeline-123" } })

    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => {
      expect(toolsService.createTool).toHaveBeenCalledWith(
        expect.objectContaining({
          implementation_type: "rag_retrieval",
          implementation_config: expect.objectContaining({ pipeline_id: "pipeline-123" }),
        })
      )
    })
  })

  it.skip("creates agent_call tool with target slug and timeout", async () => {
    render(<ToolsPage />)

    await waitFor(() => expect(toolsService.listTools).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "New Tool" }))
    fireEvent.change(screen.getByPlaceholderText("Web Search"), { target: { value: "Agent Caller" } })
    fireEvent.change(screen.getByPlaceholderText("web-search"), { target: { value: "agent-caller" } })
    fireEvent.change(
      screen.getByPlaceholderText("Search the web for current information..."),
      { target: { value: "calls published agent" } }
    )

    const comboboxes = screen.getAllByRole("combobox")
    const implementationSelect = comboboxes[comboboxes.length - 1]
    fireEvent.mouseDown(implementationSelect)
    fireEvent.click(await screen.findByText("Agent Call"))

    fireEvent.change(screen.getByPlaceholderText("target_agent_slug (recommended)"), { target: { value: "child-agent" } })
    fireEvent.change(screen.getByPlaceholderText("timeout_s (optional, default 60)"), { target: { value: "30" } })
    fireEvent.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => {
      expect(toolsService.createTool).toHaveBeenCalledWith(
        expect.objectContaining({
          implementation_type: "agent_call",
          implementation_config: expect.objectContaining({ target_agent_slug: "child-agent" }),
          execution_config: expect.objectContaining({ timeout_s: 30 }),
        })
      )
    })
  })
})
