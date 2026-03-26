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
      return [
        { key: "openai", label: "OpenAI" },
        { key: "local", label: "Local" },
        { key: "custom", label: "Custom" },
      ]
    }
    return [
      { key: "openai", label: "OpenAI" },
      { key: "anthropic", label: "Anthropic" },
      { key: "google", label: "Google AI" },
      { key: "xai", label: "xAI" },
      { key: "local", label: "Local" },
      { key: "custom", label: "Custom" },
    ]
  }),
  isTenantManagedPricingProvider: jest.fn((provider: string) => provider === "local" || provider === "custom"),
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
    name: "Built-in Model",
    description: "Built-in priced",
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
        pricing_config: {
          currency: "USD",
          billing_mode: "per_1k_tokens",
          rates: { input: 0.001, output: 0.002 },
        },
      },
    ],
  },
  {
    id: "model-2",
    name: "Custom Model",
    description: "Tenant priced",
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
        id: "provider-2",
        provider: "custom",
        provider_model_id: "my-gateway-chat",
        priority: 1,
        is_enabled: true,
        config: {},
        credentials_ref: null,
        pricing_config: {
          currency: "USD",
          billing_mode: "per_1k_tokens",
          rates: { input: 0.002, output: 0.006 },
        },
      },
    ],
  },
  {
    id: "model-3",
    name: "Embedding Model",
    description: "Vectors",
    capability_type: "embedding",
    metadata: {},
    default_resolution_policy: {},
    version: 1,
    status: "active",
    tenant_id: null,
    created_at: "",
    updated_at: "",
    providers: [
      {
        id: "provider-3",
        provider: "openai",
        provider_model_id: "text-embedding-3-large",
        priority: 0,
        is_enabled: true,
        config: {},
        credentials_ref: null,
        pricing_config: {
          currency: "USD",
          billing_mode: "unknown",
        },
      },
    ],
  },
]

describe("Models Registry", () => {
  beforeEach(() => {
    ;(modelsService.listModels as jest.Mock).mockResolvedValue({
      models: mockModels,
      total: mockModels.length,
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

  it("shows platform-managed pricing note for built-in providers", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    const editProviderButton = await screen.findByTestId("edit-provider-provider-1")
    fireEvent.click(editProviderButton)

    expect(await screen.findByText(/Platform-managed pricing/i)).toBeInTheDocument()
    expect(screen.queryByLabelText("Input Rate")).not.toBeInTheDocument()
  })

  it("opens custom provider dialog and saves pricing changes", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    const editProviderButton = await screen.findByTestId("edit-provider-provider-2")
    fireEvent.click(editProviderButton)

    const priorityInput = await screen.findByLabelText("Priority (lower = higher priority)")
    fireEvent.change(priorityInput, { target: { value: "2" } })

    const inputRate = await screen.findByLabelText("Input Rate")
    fireEvent.change(inputRate, { target: { value: "0.003" } })

    const saveButton = await screen.findByText("Save")
    fireEvent.click(saveButton)

    await waitFor(() =>
      expect(modelsService.updateProvider).toHaveBeenCalledWith(
        "model-2",
        "provider-2",
        expect.objectContaining({
          priority: 2,
          pricing_config: expect.objectContaining({
            billing_mode: "per_1k_tokens",
            rates: expect.objectContaining({ input: 0.003 }),
          }),
        })
      )
    )
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
    expect(screen.queryByText("Built-in Model")).not.toBeInTheDocument()
  })

  it("renders global models as read-only", async () => {
    render(<ModelsPage />)

    await waitFor(() => expect(modelsService.listModels).toHaveBeenCalled())

    expect(screen.getByText("Global")).toBeInTheDocument()
    expect(screen.getByText("Global models are read-only.")).toBeInTheDocument()
    expect(screen.queryByTestId("edit-model-model-3")).not.toBeInTheDocument()
    expect(screen.queryByTestId("edit-provider-provider-3")).not.toBeInTheDocument()
  })
})
