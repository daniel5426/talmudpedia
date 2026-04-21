import { settingsApiKeysService } from "@/services/settings-api-keys"

const getMock = jest.fn()
const postMock = jest.fn()
const deleteMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}))

describe("settings api keys service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("lists organization api keys", async () => {
    getMock.mockResolvedValue([])
    await settingsApiKeysService.listApiKeys({ owner_scope: "organization" })
    expect(getMock).toHaveBeenCalledWith("/api/settings/api-keys?owner_scope=organization")
  })

  it("creates project api keys", async () => {
    postMock.mockResolvedValue({ api_key: { id: "1" }, token: "ppk_x", token_type: "bearer" })
    await settingsApiKeysService.createApiKey({ owner_scope: "project", project_id: "project-1", name: "Build Key" })
    expect(postMock).toHaveBeenCalledWith("/api/settings/api-keys", {
      owner_scope: "project",
      project_id: "project-1",
      name: "Build Key",
      scopes: ["agents.embed"],
    })
  })

  it("revokes and deletes scoped api keys", async () => {
    postMock.mockResolvedValue({ api_key: { id: "1", status: "revoked" } })
    deleteMock.mockResolvedValue(undefined)
    await settingsApiKeysService.revokeApiKey("1", { owner_scope: "project", project_id: "project-1" })
    await settingsApiKeysService.deleteApiKey("1", { owner_scope: "organization" })
    expect(postMock).toHaveBeenCalledWith("/api/settings/api-keys/1/revoke?owner_scope=project&project_id=project-1")
    expect(deleteMock).toHaveBeenCalledWith("/api/settings/api-keys/1?owner_scope=organization")
  })
})
