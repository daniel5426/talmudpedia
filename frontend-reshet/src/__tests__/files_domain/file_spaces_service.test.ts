import { fileSpacesService } from "@/services/file-spaces"

const getMock = jest.fn()
const postMock = jest.fn()
const putMock = jest.fn()
const deleteMock = jest.fn()
const requestRawMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    baseUrl: "/api/py",
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
    requestRaw: (...args: unknown[]) => requestRawMock(...args),
  },
  HttpRequestError: class HttpRequestError extends Error {
    constructor(
      message: string,
      public readonly status: number,
      public readonly detail: unknown,
    ) {
      super(message)
    }
  },
}))

describe("file spaces service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("lists file spaces from the admin files endpoint", async () => {
    getMock.mockResolvedValue({ items: [] })

    await fileSpacesService.list()

    expect(getMock).toHaveBeenCalledWith("/admin/files")
  })

  it("encodes text-read paths and exposes download urls", async () => {
    getMock.mockResolvedValue({ entry: {}, revision: {}, content: "x" })

    await fileSpacesService.readText("space-1", "raw/listings notes.md")

    expect(getMock).toHaveBeenCalledWith(
      "/admin/files/space-1/entries/content?path=raw%2Flistings%20notes.md",
    )
    expect(fileSpacesService.buildDownloadUrl("space-1", "raw/listings notes.md")).toBe(
      "/api/py/admin/files/space-1/entries/download?path=raw%2Flistings%20notes.md",
    )
  })

  it("posts file move requests to the move endpoint", async () => {
    postMock.mockResolvedValue({ items: [] })

    await fileSpacesService.move("space-1", {
      from_path: "raw/listings/notes.md",
      to_path: "normalized/report.md",
    })

    expect(postMock).toHaveBeenCalledWith("/admin/files/space-1/entries/move", {
      from_path: "raw/listings/notes.md",
      to_path: "normalized/report.md",
    })
  })

  it("fetches binary blobs from the download endpoint", async () => {
    const blobMock = jest.fn().mockResolvedValue({ kind: "blob" })
    requestRawMock.mockResolvedValue({
      ok: true,
      blob: blobMock,
    })

    const blob = await fileSpacesService.fetchBlob("space-1", "folder/image 1.png")

    expect(requestRawMock).toHaveBeenCalledWith(
      "/admin/files/space-1/entries/download?path=folder%2Fimage%201.png",
      { method: "GET", signal: undefined },
    )
    expect(blobMock).toHaveBeenCalled()
    expect(blob).toEqual({ kind: "blob" })
  })
})
