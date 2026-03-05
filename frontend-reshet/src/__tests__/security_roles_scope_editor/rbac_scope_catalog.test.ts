import { rbacService } from "@/services/rbac"

const getMock = jest.fn()
const postMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}))

describe("rbac scope-key api", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("fetches scope catalog for tenant", async () => {
    getMock.mockResolvedValue({ groups: { agents: ["agents.read"] } })

    await rbacService.getScopeCatalog("tenant-slug")

    expect(getMock).toHaveBeenCalledWith("/api/tenants/tenant-slug/scope-catalog")
  })

  it("creates role using scope-key permissions", async () => {
    postMock.mockResolvedValue({ id: "role-1" })

    await rbacService.createRole("tenant-slug", {
      name: "editor",
      description: "edits",
      permissions: ["agents.write", "models.write"],
    })

    expect(postMock).toHaveBeenCalledWith("/api/tenants/tenant-slug/roles", {
      name: "editor",
      description: "edits",
      permissions: ["agents.write", "models.write"],
    })
  })
})
