import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import ModelsPage from "@/app/admin/models/page"
import { modelsService, credentialsService } from "@/services"

jest.mock("@/services", () => ({
  modelsService: {
    listModels: jest.fn(),
    updateModel: jest.fn(),
    updateProvider: jest.fn(),
    addProvider: jest.fn(),
    deleteModel: jest.fn(),
    removeProvider: jest.fn(),
  },
  credentialsService: {
    listCredentials: jest.fn(),
  },
}))

jest.mock("@/contexts/TenantContext", () => ({
  useTenant: () => ({ currentTenant: { id: "tenant-1", slug: "tenant-1" } }),
}))

jest.mock("@/components/direction-provider", () => ({
  useDirection: () => ({ direction: "ltr" }),
}))

const mockModels = [
  {
    id: "model-1",
    name: "Test Model",
    slug: "test-model",
    description: "Test",
    capability_type: "chat",
    metadata: {},
    default_resolution_policy: {},
    version: 1,
    status: "active",
    tenant_id: "tenant-1",
    created_at: "",
    updated_at: "",
    providers: [
      {
        id: "provider-1",
        provider: "openai",
        provider_model_id: "gpt-4o",
        priority: 0,
        is_enabled: true,
        config: {},
        credentials_ref: null,
      },
    ],
  },
]

describe("Models Registry", () => {
  beforeEach(() => {
    ;(modelsService.listModels as jest.Mock).mockResolvedValue({
      models: mockModels,
      total: 1,
    })
    ;(credentialsService.listCredentials as jest.Mock).mockResolvedValue([])
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it("opens edit model dialog and saves changes", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    const editButton = await screen.findByTestId("edit-model-model-1")
    fireEvent.click(editButton)

    const nameInput = await screen.findByLabelText("Name")
    fireEvent.change(nameInput, { target: { value: "Updated Model" } })

    const saveButton = await screen.findByText("Save Changes")
    fireEvent.click(saveButton)

    await waitFor(() => expect(modelsService.updateModel).toHaveBeenCalled())
  })

  it("opens edit provider dialog and saves changes", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    const editProviderButton = await screen.findByTestId("edit-provider-provider-1")
    fireEvent.click(editProviderButton)

    const priorityInput = await screen.findByLabelText("Priority (lower = higher priority)")
    fireEvent.change(priorityInput, { target: { value: "2" } })

    const saveButton = await screen.findByText("Save")
    fireEvent.click(saveButton)

    await waitFor(() => expect(modelsService.updateProvider).toHaveBeenCalled())
  })
})
