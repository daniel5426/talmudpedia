import { fireEvent, render, screen } from "@testing-library/react"

import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"

jest.mock("@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader", () => ({
  ArtifactWorkspaceSidebarHeader: () => <div>Sidebar Header</div>,
}))

jest.mock("@/components/admin/artifacts/ArtifactWorkspaceTabs", () => ({
  ArtifactWorkspaceTabs: () => <div>Tabs</div>,
}))

jest.mock("@/components/admin/artifacts/ArtifactCredentialCodeEditor", () => ({
  ArtifactCredentialCodeEditor: () => <div>Code Editor</div>,
}))

describe("artifact workspace editor", () => {
  it("opens the per-file action menu on double click", () => {
    render(
      <ArtifactWorkspaceEditor
        sourceFiles={[
          {
            path: "src/main.py",
            content: "print('hello')",
          },
        ]}
        language="python"
        activeFilePath="src/main.py"
        onActiveFileChange={jest.fn()}
        onSourceFilesChange={jest.fn()}
      />
    )

    const fileButton = screen.getByRole("button", { name: "main.py" })
    fireEvent.click(fileButton, {
      clientX: 140,
      clientY: 220,
      timeStamp: 1000,
    })
    fireEvent.click(fileButton, {
      clientX: 140,
      clientY: 220,
      timeStamp: 1120,
    })

    expect(screen.getByText("Download file")).toBeInTheDocument()
    expect(screen.getByText("Copy path")).toBeInTheDocument()
    expect(screen.getByText("Delete")).toBeInTheDocument()
  })

  it("downloads the selected source file from the action menu", () => {
    const originalCreateObjectURL = URL.createObjectURL
    const originalRevokeObjectURL = URL.revokeObjectURL
    const createObjectURL = jest.fn(() => "blob:test")
    const revokeObjectURL = jest.fn()

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    })

    render(
      <ArtifactWorkspaceEditor
        sourceFiles={[
          {
            path: "src/main.py",
            content: "print('hello')",
          },
        ]}
        language="python"
        activeFilePath="src/main.py"
        onActiveFileChange={jest.fn()}
        onSourceFilesChange={jest.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "main.py" }), {
      clientX: 140,
      clientY: 220,
      timeStamp: 1000,
    })
    fireEvent.click(screen.getByRole("button", { name: "main.py" }), {
      clientX: 140,
      clientY: 220,
      timeStamp: 1120,
    })
    fireEvent.click(screen.getByText("Download file"))

    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test")

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: originalCreateObjectURL,
    })
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: originalRevokeObjectURL,
    })
  })

  it("does not open the per-file action menu on a single click", () => {
    render(
      <ArtifactWorkspaceEditor
        sourceFiles={[
          {
            path: "src/main.py",
            content: "print('hello')",
          },
        ]}
        language="python"
        activeFilePath="src/main.py"
        onActiveFileChange={jest.fn()}
        onSourceFilesChange={jest.fn()}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "main.py" }), {
      clientX: 140,
      clientY: 220,
    })

    expect(screen.queryByText("Download file")).not.toBeInTheDocument()
  })
})
