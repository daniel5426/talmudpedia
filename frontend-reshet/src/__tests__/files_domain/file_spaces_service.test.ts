import { fileSpacesService } from "@/services/file-spaces"

const getMock = jest.fn()
const postMock = jest.fn()
const putMock = jest.fn()
const deleteMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    baseUrl: "/api/py",
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
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
})
