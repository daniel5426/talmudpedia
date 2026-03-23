import { render, screen, waitFor, fireEvent } from "@testing-library/react"
import ModelsPage from "@/app/admin/models/page"
import { modelsService, credentialsService } from "@/services"

jest.mock("@/services", () => ({
  modelsService: {
    listModels: jest.fn(),
    createModel: jest.fn(),
    updateModel: jest.fn(),
    updateProvider: jest.fn(),
    addProvider: jest.fn(),
    deleteModel: jest.fn(),
    removeProvider: jest.fn(),
  },
  credentialsService: {
    listCredentials: jest.fn(),
  },
  LLM_PROVIDER_OPTIONS: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "gemini", label: "Google Gemini" },
    { key: "azure", label: "Azure OpenAI" },
    { key: "cohere", label: "Cohere" },
    { key: "groq", label: "Groq" },
    { key: "mistral", label: "Mistral" },
    { key: "together", label: "Together AI" },
    { key: "huggingface", label: "HuggingFace" },
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  getModelProviderOptions: jest.fn((capability: string) => {
    if (capability === "embedding") {
      return [{ key: "openai", label: "OpenAI" }]
    }
    return [
      { key: "openai", label: "OpenAI" },
      { key: "anthropic", label: "Anthropic" },
      { key: "google", label: "Google AI" },
      { key: "xai", label: "xAI" },
    ]
  }),
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
  {
    id: "model-2",
    name: "Embedding Model",
    description: "Vectors",
    capability_type: "embedding",
    metadata: {},
    default_resolution_policy: {},
    version: 1,
    status: "active",
    tenant_id: "tenant-1",
    created_at: "",
    updated_at: "",
    providers: [
      {
        id: "provider-2",
        provider: "openai",
        provider_model_id: "text-embedding-3-large",
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
    ;(credentialsService.listCredentials as jest.Mock).mockResolvedValue([
      {
        id: "cred-1",
        tenant_id: "tenant-1",
        category: "llm_provider",
        provider_key: "openai",
        provider_variant: null,
        display_name: "OpenAI Tenant",
        credential_keys: ["api_key"],
        is_enabled: true,
        is_default: true,
        created_at: "",
        updated_at: "",
      },
    ])
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

  it("creates a model without asking for a slug", async () => {
    render(<ModelsPage />)

    fireEvent.click(await screen.findByText("New Model"))
    expect(screen.queryByLabelText(/slug/i)).not.toBeInTheDocument()

    fireEvent.change(await screen.findByLabelText("Name"), {
      target: { value: "Fresh Model" },
    })
    fireEvent.click(await screen.findByText("Create"))

    await waitFor(() =>
      expect(modelsService.createModel).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Fresh Model",
          capability_type: "chat",
        })
      )
    )
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

  it("shows platform default label when provider has no explicit credential", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())
    expect((await screen.findAllByText(/Platform Default/)).length).toBeGreaterThan(0)
  })

  it("filters the models list from the search input", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    fireEvent.change(await screen.findByPlaceholderText("Search models..."), {
      target: { value: "embedding" },
    })

    expect(screen.getByText("Embedding Model")).toBeInTheDocument()
    expect(screen.queryByText("Test Model")).not.toBeInTheDocument()
  })
})
