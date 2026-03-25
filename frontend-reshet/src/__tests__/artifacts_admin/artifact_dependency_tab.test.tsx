import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { ArtifactDependencyTab } from "@/components/admin/artifacts/ArtifactDependencyTab"

const analyzeDependencies = jest.fn()
const verifyPythonPackage = jest.fn()

jest.mock("@/services/artifacts", () => ({
  artifactsService: {
    analyzeDependencies: (...args: unknown[]) => analyzeDependencies(...args),
    verifyPythonPackage: (...args: unknown[]) => verifyPythonPackage(...args),
  },
}))

describe("ArtifactDependencyTab", () => {
  beforeEach(() => {
    analyzeDependencies.mockReset()
    verifyPythonPackage.mockReset()
  })

  it("renders analyzed rows and removes declared dependencies", async () => {
    const onChangeDependencies = jest.fn()
    analyzeDependencies.mockResolvedValue({
      rows: [
        {
          name: "json",
          normalized_name: "json",
          declared_spec: null,
          classification: "builtin",
          source: "builtin",
          status: "Built-in",
          note: "Imported from the runtime standard library.",
          imported: true,
          declared: false,
          can_remove: false,
          can_add: false,
          needs_declaration: false,
        },
        {
          name: "openai",
          normalized_name: "openai",
          declared_spec: "openai",
          classification: "declared",
          source: "declared",
          status: "Declared",
          note: "Imported and declared.",
          imported: true,
          declared: true,
          can_remove: true,
          can_add: false,
          needs_declaration: false,
        },
      ],
    })

    render(
      <ArtifactDependencyTab
        language="python"
        sourceFiles={[{ path: "main.py", content: "import json\nimport openai\n" }]}
        dependencies="openai, pydantic"
        onChangeDependencies={onChangeDependencies}
      />,
    )

    expect(await screen.findByText("json")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /remove/i }))

    expect(onChangeDependencies).toHaveBeenCalledWith("pydantic")
  })

  it("verifies Python dependencies before adding them", async () => {
    const onChangeDependencies = jest.fn()
    analyzeDependencies.mockResolvedValue({ rows: [] })
    verifyPythonPackage.mockResolvedValue({
      package_name: "OpenAI",
      normalized_name: "openai",
      status: "exists",
      exists: true,
      error_message: null,
    })

    render(
      <ArtifactDependencyTab
        language="python"
        sourceFiles={[]}
        dependencies=""
        onChangeDependencies={onChangeDependencies}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText("Add Python package from PyPI"), { target: { value: "OpenAI" } })
    fireEvent.click(screen.getByRole("button", { name: /add dependency/i }))

    await waitFor(() => {
      expect(verifyPythonPackage).toHaveBeenCalledWith({ package_name: "OpenAI" }, undefined)
      expect(onChangeDependencies).toHaveBeenCalledWith("openai")
    })
  })

  it("shows a duplicate error instead of adding the same dependency twice", async () => {
    const onChangeDependencies = jest.fn()
    analyzeDependencies.mockResolvedValue({ rows: [] })
    verifyPythonPackage.mockResolvedValue({
      package_name: "openai",
      normalized_name: "openai",
      status: "exists",
      exists: true,
      error_message: null,
    })

    render(
      <ArtifactDependencyTab
        language="python"
        sourceFiles={[]}
        dependencies="openai"
        onChangeDependencies={onChangeDependencies}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText("Add Python package from PyPI"), { target: { value: "openai" } })
    fireEvent.click(screen.getByRole("button", { name: /add dependency/i }))

    expect(await screen.findByText("Dependency `openai` is already declared.")).toBeInTheDocument()
    expect(onChangeDependencies).not.toHaveBeenCalled()
  })
})
