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

  it("lists and updates projects", async () => {
    getMock.mockResolvedValue([])
    patchMock.mockResolvedValue({ id: "p1", slug: "alpha" })

    await settingsProjectsService.listProjects()
    await settingsProjectsService.getProject("alpha")
    await settingsProjectsService.listProjectMembers("alpha")
    await settingsProjectsService.updateProject("alpha", { name: "Alpha 2" })

    expect(getMock).toHaveBeenNthCalledWith(1, "/api/settings/projects")
    expect(getMock).toHaveBeenNthCalledWith(2, "/api/settings/projects/alpha")
    expect(getMock).toHaveBeenNthCalledWith(3, "/api/settings/projects/alpha/members")
    expect(patchMock).toHaveBeenCalledWith("/api/settings/projects/alpha", { name: "Alpha 2" })
  })
})
