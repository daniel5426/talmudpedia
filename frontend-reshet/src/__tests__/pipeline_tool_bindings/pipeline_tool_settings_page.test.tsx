import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import PipelineEditorPage from "@/app/admin/pipelines/[id]/page"

const pushMock = jest.fn()
const replaceMock = jest.fn()
const listVisualPipelinesMock = jest.fn()
const getOperatorCatalogMock = jest.fn()
const listOperatorSpecsMock = jest.fn()
const getPipelineToolBindingMock = jest.fn()
const updatePipelineToolBindingMock = jest.fn()

const searchParamsState = { jobId: null as string | null, toolSettings: "1" as string | null }
const tenantContext = { currentTenant: { slug: "tenant-1" } }
const routerMock = { push: pushMock, replace: replaceMock }
const paramsMock = { id: "pipeline-123" }
const searchParamsMock = {
  get: (key: string) => {
    if (key === "jobId") return searchParamsState.jobId
    if (key === "toolSettings") return searchParamsState.toolSettings
    return null
  },
}

jest.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useParams: () => paramsMock,
  useSearchParams: () => searchParamsMock,
}))

jest.mock("@/contexts/TenantContext", () => ({
  useTenant: () => tenantContext,
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

jest.mock("@/services", () => ({
  ragAdminService: {
    listVisualPipelines: (...args: unknown[]) => listVisualPipelinesMock(...args),
    getOperatorCatalog: (...args: unknown[]) => getOperatorCatalogMock(...args),
    listOperatorSpecs: (...args: unknown[]) => listOperatorSpecsMock(...args),
    getPipelineToolBinding: (...args: unknown[]) => getPipelineToolBindingMock(...args),
    updatePipelineToolBinding: (...args: unknown[]) => updatePipelineToolBindingMock(...args),
  },
}))

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: () => <div data-testid="breadcrumb" />,
}))

jest.mock("@/components/admin/AdminPageHeader", () => ({
  AdminPageHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/pipeline", () => ({
  PipelineBuilder: () => <div data-testid="pipeline-builder" />,
}))

jest.mock("@/components/pipeline/RunPipelineDialog", () => ({
  RunPipelineDialog: () => null,
}))

jest.mock("@/components/builder", () => ({
  HeaderConfigEditor: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe("pipeline tool settings page", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    searchParamsState.jobId = null
    searchParamsState.toolSettings = "1"

    getOperatorCatalogMock.mockResolvedValue({})
    listOperatorSpecsMock.mockResolvedValue({})
    listVisualPipelinesMock.mockResolvedValue({
      pipelines: [
        {
          id: "pipeline-123",
          tenant_id: "tenant-1",
          name: "Retrieval Pipeline",
          description: "Pipeline description",
          pipeline_type: "retrieval",
          nodes: [],
          edges: [],
          version: 1,
          is_published: false,
          created_at: "2026-03-19T00:00:00Z",
          updated_at: "2026-03-19T00:00:00Z",
        },
      ],
    })
    getPipelineToolBindingMock.mockResolvedValue({
      enabled: true,
      tool_id: "tool-123",
      tool_name: "Retrieval Assistant Tool",
      tool_slug: "retrieval-pipeline-pipeline-123",
      status: "draft",
      description: "Use this tool for normalized retrieval.",
      input_schema: {
        type: "object",
        properties: {
          text: { type: "string" },
        },
        additionalProperties: false,
      },
      output_schema: { type: "object", additionalProperties: true },
      visual_pipeline_id: "pipeline-123",
      executable_pipeline_id: null,
    })
    updatePipelineToolBindingMock.mockResolvedValue({
      enabled: true,
      tool_id: "tool-123",
      tool_name: "Updated Retrieval Tool",
      tool_slug: "retrieval-pipeline-pipeline-123",
      status: "draft",
      description: "Updated description",
      input_schema: {
        type: "object",
        properties: {
          query: { type: "string" },
        },
        additionalProperties: false,
      },
      output_schema: { type: "object", additionalProperties: true },
      visual_pipeline_id: "pipeline-123",
      executable_pipeline_id: null,
    })
  })

  it("loads and saves pipeline-owned tool settings including tool name", async () => {
    render(<PipelineEditorPage />)

    expect(await screen.findByDisplayValue("Retrieval Assistant Tool")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Use this tool for normalized retrieval.")).toBeInTheDocument()
    expect(screen.getByText(/Tool ID:/)).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Agent-facing tool name"), {
      target: { value: "Updated Retrieval Tool" },
    })
    fireEvent.change(screen.getByPlaceholderText("Describe when the agent should call this pipeline tool."), {
      target: { value: "Updated description" },
    })
    fireEvent.change(screen.getByPlaceholderText('{"type":"object","properties":{}}'), {
      target: { value: JSON.stringify({ type: "object", properties: { query: { type: "string" } }, additionalProperties: false }, null, 2) },
    })

    fireEvent.click(screen.getByRole("button", { name: "Save Tool Settings" }))

    await waitFor(() => {
      expect(updatePipelineToolBindingMock).toHaveBeenCalledWith(
        "pipeline-123",
        {
          enabled: true,
          tool_name: "Updated Retrieval Tool",
          description: "Updated description",
          input_schema: {
            type: "object",
            properties: {
              query: { type: "string" },
            },
            additionalProperties: false,
          },
        },
        "tenant-1"
      )
    })

    expect(await screen.findByDisplayValue("Updated Retrieval Tool")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Updated description")).toBeInTheDocument()
  })
})
