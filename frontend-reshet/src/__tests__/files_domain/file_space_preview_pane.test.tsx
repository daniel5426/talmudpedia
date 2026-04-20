import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { FileSpacePreviewPane } from "@/components/admin/files/FileSpacePreviewPane"

const fetchBlobMock = jest.fn()
const buildDownloadUrlMock = jest.fn(() => "/download")
const renderAsyncMock = jest.fn()

jest.mock("@/components/admin/files/FileSpacePdfPreview", () => ({
  FileSpacePdfPreview: () => <div>PDF Preview</div>,
}))

jest.mock("@/components/admin/files/FileSpaceWorkbookPreview", () => ({
  FileSpaceWorkbookPreview: () => <div>Workbook Preview</div>,
}))

jest.mock("docx-preview", () => ({
  renderAsync: (...args: unknown[]) => renderAsyncMock(...args),
}))

jest.mock("@/services", () => ({
  fileSpacesService: {
    fetchBlob: (...args: unknown[]) => fetchBlobMock(...args),
    buildDownloadUrl: (...args: unknown[]) => buildDownloadUrlMock(...args),
  },
}))

describe("file space preview pane", () => {
  beforeAll(() => {
    Object.defineProperty(URL, "createObjectURL", {
      writable: true,
      value: jest.fn(() => "blob:preview"),
    })
    Object.defineProperty(URL, "revokeObjectURL", {
      writable: true,
      value: jest.fn(),
    })
  })

  beforeEach(() => {
    jest.clearAllMocks()
    renderAsyncMock.mockImplementation(async (_data, container: HTMLElement) => {
      const marker = document.createElement("div")
      marker.textContent = "DOCX Preview"
      container.appendChild(marker)
      return {}
    })
  })

  it("renders image previews from fetched blobs", async () => {
    fetchBlobMock.mockResolvedValue(new Blob(["image-bytes"], { type: "image/png" }))

    render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-1",
          space_id: "space-1",
          path: "photo.png",
          name: "photo.png",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-1",
          mime_type: "image/png",
          byte_size: 10,
          sha256: "abc",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    expect(await screen.findByAltText("Preview of photo.png")).toBeInTheDocument()
    expect(fetchBlobMock).toHaveBeenCalledWith("space-1", "photo.png")
  })

  it("renders pdf previews in-app", async () => {
    fetchBlobMock.mockResolvedValue(new Blob(["pdf-bytes"], { type: "application/pdf" }))

    render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-2",
          space_id: "space-1",
          path: "guide.pdf",
          name: "guide.pdf",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-2",
          mime_type: "application/pdf",
          byte_size: 10,
          sha256: "def",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    expect(await screen.findByText("PDF Preview")).toBeInTheDocument()
  })

  it("renders docx previews in-app", async () => {
    fetchBlobMock.mockResolvedValue({
      arrayBuffer: jest.fn().mockResolvedValue(new ArrayBuffer(16)),
    } as unknown as Blob)

    render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-3",
          space_id: "space-1",
          path: "brief.docx",
          name: "brief.docx",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-3",
          mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          byte_size: 10,
          sha256: "ghi",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    expect(await screen.findByText("DOCX Preview")).toBeInTheDocument()
    expect(screen.getByLabelText("Document preview")).toBeInTheDocument()
    expect(screen.getByText("100%")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reset document zoom" })).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }))
    expect(screen.getByText("120%")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reset document zoom" })).toBeEnabled()
    const zoomLayer = screen.getByTestId("docx-zoom-layer")
    expect(zoomLayer.className).toContain("cursor-grab")
    await waitFor(() => {
      expect(renderAsyncMock).toHaveBeenCalled()
    })
  })

  it("renders workbook previews in-app", async () => {
    fetchBlobMock.mockResolvedValue(new Blob(["xlsx-bytes"], { type: "application/vnd.ms-excel" }))

    render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-4",
          space_id: "space-1",
          path: "sheet.xlsx",
          name: "sheet.xlsx",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-4",
          mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          byte_size: 10,
          sha256: "jkl",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    expect(await screen.findByText("Workbook Preview")).toBeInTheDocument()
    expect(fetchBlobMock).toHaveBeenCalledWith("space-1", "sheet.xlsx")
  })

  it("keeps unsupported files download-only", async () => {
    render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-unsupported",
          space_id: "space-1",
          path: "archive.zip",
          name: "archive.zip",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-unsupported",
          mime_type: "application/zip",
          byte_size: 10,
          sha256: "jkl",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    expect(screen.getByText("Preview unavailable")).toBeInTheDocument()
    expect(fetchBlobMock).not.toHaveBeenCalled()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("ignores late preview results after unmount", async () => {
    let resolveBlob: ((value: Blob) => void) | null = null
    fetchBlobMock.mockImplementation(
      () =>
        new Promise<Blob>((resolve) => {
          resolveBlob = resolve
        }),
    )

    const { unmount } = render(
      <FileSpacePreviewPane
        spaceId="space-1"
        entry={{
          id: "entry-5",
          space_id: "space-1",
          path: "photo.png",
          name: "photo.png",
          parent_path: null,
          entry_type: "file",
          current_revision_id: "rev-5",
          mime_type: "image/png",
          byte_size: 10,
          sha256: "mno",
          is_text: false,
          deleted_at: null,
          created_at: null,
          updated_at: null,
        }}
      />,
    )

    unmount()
    resolveBlob?.(new Blob(["image-bytes"], { type: "image/png" }))

    await waitFor(() => {
      expect(URL.createObjectURL).not.toHaveBeenCalled()
    })
  })
})
