import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import PipelineEditorPage from "@/app/admin/pipelines/[id]/page"

const pushMock = jest.fn()
const replaceMock = jest.fn()
const listVisualPipelinesMock = jest.fn()
const getOperatorCatalogMock = jest.fn()
const listOperatorSpecsMock = jest.fn()
const getPipelineToolBindingMock = jest.fn()
const listPipelineVersionsMock = jest.fn()

const tenantContext = { currentTenant: { slug: "tenant-1" } }
const routerMock = { push: pushMock, replace: replaceMock }
const searchParamsMock = { get: () => null }

jest.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useParams: () => ({ id: "pipeline-123" }),
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
    listPipelineVersions: (...args: unknown[]) => listPipelineVersionsMock(...args),
  },
}))

jest.mock("@/components/ui/custom-breadcrumb", () => ({
  CustomBreadcrumb: () => <div data-testid="breadcrumb" />,
}))

jest.mock("@/components/admin/AdminPageHeader", () => ({
  AdminPageHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/pipeline", () => ({
  PipelineBuilder: ({ onRun }: { onRun?: () => void }) => (
    <button type="button" onClick={onRun}>
      Open Run
    </button>
  ),
}))

jest.mock("@/components/pipeline/RunPipelineDialog", () => ({
  RunPipelineDialog: () => null,
}))

jest.mock("@/components/builder", () => ({
  HeaderConfigEditor: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
}))

jest.mock("@/components/shared/PromptMentionInput", () => ({
  PromptMentionInput: () => null,
}))

jest.mock("@/components/shared/PromptMentionJsonEditor", () => ({
  PromptMentionJsonEditor: () => <textarea placeholder='{"type":"object","properties":{}}' readOnly />,
  fillPromptMentionJsonToken: (value: string) => value,
}))

jest.mock("@/components/shared/PromptModal", () => ({
  PromptModal: () => null,
}))

jest.mock("@/components/shared/usePromptMentionModal", () => ({
  usePromptMentionModal: () => ({
    open: false,
    promptId: null,
    context: null,
    openPromptMentionModal: jest.fn(),
    handleOpenChange: jest.fn(),
  }),
}))

describe("pipeline builder stale executable feedback", () => {
  beforeEach(() => {
    jest.clearAllMocks()
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
          version: 2,
          is_published: false,
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T01:00:00Z",
        },
      ],
    })
    getPipelineToolBindingMock.mockResolvedValue({
      enabled: false,
      tool_name: "Retrieval Pipeline",
      input_schema: {},
      output_schema: {},
      description: "",
      visual_pipeline_id: "pipeline-123",
      executable_pipeline_id: null,
    })
    listPipelineVersionsMock.mockResolvedValue({
      versions: [
        {
          id: "exec-1",
          version: 1,
          is_valid: true,
          created_at: "2026-04-01T00:30:00Z",
        },
      ],
    })
  })

  it("tells the user to compile again when the visual draft is newer than the latest executable", async () => {
    render(<PipelineEditorPage />)

    await screen.findByText("Open Run")
    fireEvent.click(screen.getByText("Open Run"))

    await waitFor(() => {
      expect(
        screen.getByText("Pipeline draft changed since the latest executable was created. Compile the pipeline again before running it."),
      ).toBeInTheDocument()
    })
  })
})
