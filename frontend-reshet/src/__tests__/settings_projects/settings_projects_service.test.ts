import { settingsProjectsService } from "@/services/settings-projects"

const getMock = jest.fn()
const patchMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
}))

describe("settings projects service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("lists and updates projects by id", async () => {
    getMock.mockResolvedValue([])
    patchMock.mockResolvedValue({ id: "p1" })

    await settingsProjectsService.listProjects()
    await settingsProjectsService.getProject("p1")
    await settingsProjectsService.listProjectMembers("p1")
    await settingsProjectsService.updateProject("p1", { name: "Alpha 2" })

    expect(getMock).toHaveBeenNthCalledWith(1, "/api/settings/projects")
    expect(getMock).toHaveBeenNthCalledWith(2, "/api/settings/projects/p1")
    expect(getMock).toHaveBeenNthCalledWith(3, "/api/settings/projects/p1/members")
    expect(patchMock).toHaveBeenCalledWith("/api/settings/projects/p1", { name: "Alpha 2" })
  })
})
