import { settingsPeoplePermissionsService } from "@/services/settings-people-permissions"

const getMock = jest.fn()
const postMock = jest.fn()
const patchMock = jest.fn()
const deleteMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}))

describe("settings people permissions service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("wires members, invitations, groups, roles, and assignments through canonical settings endpoints", async () => {
    getMock.mockResolvedValue([])
    postMock.mockResolvedValue({})
    patchMock.mockResolvedValue({})
    deleteMock.mockResolvedValue(undefined)

    await settingsPeoplePermissionsService.listMembers()
    await settingsPeoplePermissionsService.createInvitation({ email: "new@example.com", project_ids: ["p1"] })
    await settingsPeoplePermissionsService.createGroup({ name: "Ops", slug: "ops", type: "team" })
    await settingsPeoplePermissionsService.updateRole("r1", { name: "Admin" })
    await settingsPeoplePermissionsService.deleteRoleAssignment("a1")

    expect(getMock).toHaveBeenCalledWith("/api/settings/people/members")
    expect(postMock).toHaveBeenNthCalledWith(1, "/api/settings/people/invitations", { email: "new@example.com", project_ids: ["p1"] })
    expect(postMock).toHaveBeenNthCalledWith(2, "/api/settings/people/groups", { name: "Ops", slug: "ops", type: "team" })
    expect(patchMock).toHaveBeenCalledWith("/api/settings/people/roles/r1", { name: "Admin" })
    expect(deleteMock).toHaveBeenCalledWith("/api/settings/people/role-assignments/a1")
  })
})
