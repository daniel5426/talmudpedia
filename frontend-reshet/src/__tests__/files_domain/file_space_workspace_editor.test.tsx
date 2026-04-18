import { fireEvent, render, screen } from "@testing-library/react"

import { FileSpaceWorkspaceEditor } from "@/components/admin/files/FileSpaceWorkspaceEditor"

jest.mock("@/components/admin/artifacts/ArtifactWorkspaceSidebarHeader", () => ({
  ArtifactWorkspaceSidebarHeader: () => <div>Sidebar Header</div>,
}))

jest.mock("@/components/admin/artifacts/ArtifactWorkspaceTabs", () => ({
  ArtifactWorkspaceTabs: () => <div>Tabs</div>,
}))

describe("file space workspace editor", () => {
  it("opens a tree action menu on right click and routes download through it", () => {
    const onDownloadEntry = jest.fn()
    const onDeleteEntry = jest.fn()
    const onActiveFileChange = jest.fn()
    const setOpenTabs = jest.fn()

    render(
      <FileSpaceWorkspaceEditor
        entries={[
          {
            id: "file-1",
            space_id: "space-1",
            path: "notes.md",
            name: "notes.md",
            parent_path: null,
            entry_type: "file",
            current_revision_id: "rev-1",
            mime_type: "text/markdown",
            byte_size: 10,
            sha256: "abc",
            is_text: true,
            deleted_at: null,
            created_at: null,
            updated_at: null,
          },
        ]}
        activeFilePath="notes.md"
        onActiveFileChange={onActiveFileChange}
        onAddFolder={jest.fn()}
        onUploadFile={jest.fn()}
        onDeleteEntry={onDeleteEntry}
        onDownloadEntry={onDownloadEntry}
        onMoveEntry={jest.fn()}
        openTabs={["notes.md"]}
        setOpenTabs={setOpenTabs}
        editorContent={<div>Editor</div>}
      />,
    )

    fireEvent.contextMenu(screen.getByRole("button", { name: "notes.md" }), {
      clientX: 120,
      clientY: 180,
    })

    expect(screen.getByText("Download file")).toBeInTheDocument()
    fireEvent.click(screen.getByText("Download file"))

    expect(onDownloadEntry).toHaveBeenCalledWith("notes.md")
  })

  it("opens the action menu on double click for directories", () => {
    render(
      <FileSpaceWorkspaceEditor
        entries={[
          {
            id: "dir-1",
            space_id: "space-1",
            path: "docs",
            name: "docs",
            parent_path: null,
            entry_type: "directory",
            current_revision_id: null,
            mime_type: null,
            byte_size: null,
            sha256: null,
            is_text: false,
            deleted_at: null,
            created_at: null,
            updated_at: null,
          },
        ]}
        activeFilePath=""
        onActiveFileChange={jest.fn()}
        onAddFolder={jest.fn()}
        onUploadFile={jest.fn()}
        onDeleteEntry={jest.fn()}
        onDownloadEntry={jest.fn()}
        onMoveEntry={jest.fn()}
        openTabs={[]}
        setOpenTabs={jest.fn()}
        editorContent={<div>Editor</div>}
      />,
    )

    const directoryButton = screen.getByRole("button", { name: "docs" })
    fireEvent.click(directoryButton, {
      clientX: 160,
      clientY: 220,
      timeStamp: 1000,
    })
    fireEvent.click(directoryButton, {
      clientX: 160,
      clientY: 220,
      timeStamp: 1120,
    })

    expect(screen.getByText("Copy path")).toBeInTheDocument()
    expect(screen.queryByText("Download file")).not.toBeInTheDocument()
  })

  it("does not open the action menu on a single click", () => {
    render(
      <FileSpaceWorkspaceEditor
        entries={[
          {
            id: "file-1",
            space_id: "space-1",
            path: "notes.md",
            name: "notes.md",
            parent_path: null,
            entry_type: "file",
            current_revision_id: "rev-1",
            mime_type: "text/markdown",
            byte_size: 10,
            sha256: "abc",
            is_text: true,
            deleted_at: null,
            created_at: null,
            updated_at: null,
          },
        ]}
        activeFilePath="notes.md"
        onActiveFileChange={jest.fn()}
        onAddFolder={jest.fn()}
        onUploadFile={jest.fn()}
        onDeleteEntry={jest.fn()}
        onDownloadEntry={jest.fn()}
        onMoveEntry={jest.fn()}
        openTabs={["notes.md"]}
        setOpenTabs={jest.fn()}
        editorContent={<div>Editor</div>}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "notes.md" }), {
      clientX: 120,
      clientY: 180,
    })

    expect(screen.queryByText("Download file")).not.toBeInTheDocument()
  })
})
