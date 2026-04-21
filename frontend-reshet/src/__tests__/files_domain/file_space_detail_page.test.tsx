import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import FileSpaceDetailPage from "@/app/admin/files/[spaceId]/page"
import { DirectionProvider } from "@/components/direction-provider"

const pushMock = jest.fn()
const getMock = jest.fn()
const listTreeMock = jest.fn()
const listLinksMock = jest.fn()
const readTextMock = jest.fn()
const writeTextMock = jest.fn()
const listAgentsMock = jest.fn()

jest.mock("next/navigation", () => ({
  useParams: () => ({ spaceId: "space-1" }),
  useRouter: () => ({ push: pushMock }),
}))

jest.mock("@/services", () => ({
  agentService: {
    listAgents: (...args: unknown[]) => listAgentsMock(...args),
  },
  fileSpacesService: {
    get: (...args: unknown[]) => getMock(...args),
    listTree: (...args: unknown[]) => listTreeMock(...args),
    listLinks: (...args: unknown[]) => listLinksMock(...args),
    readText: (...args: unknown[]) => readTextMock(...args),
    writeText: (...args: unknown[]) => writeTextMock(...args),
    mkdir: jest.fn(),
    move: jest.fn(),
    uploadBlob: jest.fn(),
    archive: jest.fn(),
    upsertLink: jest.fn(),
    deleteLink: jest.fn(),
    deleteEntry: jest.fn(),
    buildDownloadUrl: jest.fn(() => "/download"),
  },
}))

describe("file space detail page", () => {
  beforeEach(() => {
    jest.clearAllMocks()

    getMock.mockResolvedValue({
      id: "space-1",
      organization_id: "organization-1",
      project_id: "project-1",
      name: "Workspace",
      description: null,
      status: "active",
      created_at: "2026-04-16T00:00:00Z",
      updated_at: "2026-04-16T00:00:00Z",
    })
    listTreeMock.mockResolvedValue({
      items: [
        {
          id: "file-1",
          space_id: "space-1",
          path: "notes.md",
          name: "notes.md",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-1",
          mime_type: "text/markdown",
          byte_size: 11,
          sha256: "abc",
          is_text: true,
          deleted_at: null,
          created_at: "2026-04-16T00:00:00Z",
          updated_at: "2026-04-16T00:00:00Z",
        },
      ],
    })
    listLinksMock.mockResolvedValue({ items: [] })
    listAgentsMock.mockResolvedValue({ items: [] })
    readTextMock.mockResolvedValue({
      entry: {
        id: "file-1",
        space_id: "space-1",
        path: "notes.md",
        name: "notes.md",
        parent_path: null,
        entry_type: "file",
        current_revision_id: "rev-1",
        mime_type: "text/markdown",
        byte_size: 11,
        sha256: "abc",
        is_text: true,
        deleted_at: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      revision: {
        id: "rev-1",
        entry_id: "file-1",
        storage_key: "key-1",
        mime_type: "text/markdown",
        byte_size: 11,
        sha256: "abc",
        is_text: true,
        encoding: "utf-8",
        created_by: null,
        created_by_run_id: null,
        created_at: "2026-04-16T00:00:00Z",
      },
      content: "hello world",
    })
    writeTextMock.mockResolvedValue({
      entry: {
        id: "file-1",
        space_id: "space-1",
        path: "notes.md",
        name: "notes.md",
        parent_path: null,
        entry_type: "file",
        current_revision_id: "rev-2",
        mime_type: "text/markdown",
        byte_size: 12,
        sha256: "def",
        is_text: true,
        deleted_at: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      revision: {
        id: "rev-2",
        entry_id: "file-1",
        storage_key: "key-2",
        mime_type: "text/markdown",
        byte_size: 12,
        sha256: "def",
        is_text: true,
        encoding: "utf-8",
        created_by: null,
        created_by_run_id: null,
        created_at: "2026-04-16T00:00:00Z",
      },
    })
  })

  it("tracks unsaved text edits and saves all dirty files with ctrl+s", async () => {
    render(
      <DirectionProvider>
        <FileSpaceDetailPage />
      </DirectionProvider>,
    )

    await waitFor(() => {
      expect(screen.getAllByText("notes.md").length).toBeGreaterThan(0)
    })

    const saveButton = screen.getByRole("button", { name: "Save" })
    expect(saveButton).toBeDisabled()

    fireEvent.click(screen.getAllByText("notes.md")[0])

    const editor = await screen.findByRole("textbox")
    expect(editor).toHaveValue("hello world")

    fireEvent.change(editor, { target: { value: "hello world!" } })

    await waitFor(() => {
      expect(saveButton).toBeEnabled()
    })
    expect(screen.getAllByLabelText("Unsaved changes")).toHaveLength(2)

    fireEvent.keyDown(window, { key: "s", ctrlKey: true })

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith("space-1", {
        path: "notes.md",
        content: "hello world!",
        mime_type: "text/markdown",
      })
    })
    await waitFor(() => {
      expect(saveButton).toBeDisabled()
    })
  })

  it("opens csv files in spreadsheet mode and saves edited cells through the text api", async () => {
    listTreeMock.mockResolvedValue({
      items: [
        {
          id: "file-csv",
          space_id: "space-1",
          path: "people.csv",
          name: "people.csv",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-csv-1",
          mime_type: "text/csv",
          byte_size: 21,
          sha256: "csv",
          is_text: true,
          deleted_at: null,
          created_at: "2026-04-16T00:00:00Z",
          updated_at: "2026-04-16T00:00:00Z",
        },
      ],
    })
    readTextMock.mockResolvedValue({
      entry: {
        id: "file-csv",
        space_id: "space-1",
        path: "people.csv",
        name: "people.csv",
        parent_path: null,
        entry_type: "file",
        current_revision_id: "rev-csv-1",
        mime_type: "text/csv",
        byte_size: 21,
        sha256: "csv",
        is_text: true,
        deleted_at: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      revision: {
        id: "rev-csv-1",
        entry_id: "file-csv",
        storage_key: "key-csv-1",
        mime_type: "text/csv",
        byte_size: 21,
        sha256: "csv",
        is_text: true,
        encoding: "utf-8",
        created_by: null,
        created_by_run_id: null,
        created_at: "2026-04-16T00:00:00Z",
      },
      content: "name,role\nAda,Editor",
    })
    writeTextMock.mockResolvedValue({
      entry: {
        id: "file-csv",
        space_id: "space-1",
        path: "people.csv",
        name: "people.csv",
        parent_path: null,
        entry_type: "file",
        current_revision_id: "rev-csv-2",
        mime_type: "text/csv",
        byte_size: 21,
        sha256: "csv-2",
        is_text: true,
        deleted_at: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      revision: {
        id: "rev-csv-2",
        entry_id: "file-csv",
        storage_key: "key-csv-2",
        mime_type: "text/csv",
        byte_size: 21,
        sha256: "csv-2",
        is_text: true,
        encoding: "utf-8",
        created_by: null,
        created_by_run_id: null,
        created_at: "2026-04-16T00:00:00Z",
      },
    })

    render(
      <DirectionProvider>
        <FileSpaceDetailPage />
      </DirectionProvider>,
    )

    await waitFor(() => {
      expect(screen.getAllByText("people.csv").length).toBeGreaterThan(0)
    })

    fireEvent.click(screen.getAllByText("people.csv")[0])

    const cell = await screen.findByLabelText("Cell B2")
    fireEvent.change(cell, { target: { value: "Author" } })

    fireEvent.keyDown(window, { key: "s", ctrlKey: true })

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith("space-1", {
        path: "people.csv",
        content: "name,role\nAda,Author",
        mime_type: "text/csv",
      })
    })
  })

  it("renders markdown preview and switches to raw text from the header toggle", async () => {
    readTextMock.mockResolvedValue({
      entry: {
        id: "file-1",
        space_id: "space-1",
        path: "notes.md",
        name: "notes.md",
        parent_path: null,
        entry_type: "file",
        current_revision_id: "rev-1",
        mime_type: "text/markdown",
        byte_size: 18,
        sha256: "abc",
        is_text: true,
        deleted_at: null,
        created_at: "2026-04-16T00:00:00Z",
        updated_at: "2026-04-16T00:00:00Z",
      },
      revision: {
        id: "rev-1",
        entry_id: "file-1",
        storage_key: "key-1",
        mime_type: "text/markdown",
        byte_size: 18,
        sha256: "abc",
        is_text: true,
        encoding: "utf-8",
        created_by: null,
        created_by_run_id: null,
        created_at: "2026-04-16T00:00:00Z",
      },
      content: "# Hello\n\nParagraph",
    })

    render(
      <DirectionProvider>
        <FileSpaceDetailPage />
      </DirectionProvider>,
    )

    await waitFor(() => {
      expect(screen.getAllByText("notes.md").length).toBeGreaterThan(0)
    })

    fireEvent.click(screen.getAllByText("notes.md")[0])

    expect(await screen.findByRole("heading", { name: "Hello" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Switch to raw text view" }))
    expect(await screen.findByRole("textbox")).toHaveValue("# Hello\n\nParagraph")
  })
})
