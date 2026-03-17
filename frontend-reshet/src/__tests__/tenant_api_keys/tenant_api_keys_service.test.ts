import { tenantAPIKeysService } from "@/services/tenant-api-keys"

const getMock = jest.fn()
const postMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}))

describe("tenant API keys service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("lists API keys via GET /admin/security/api-keys", async () => {
    getMock.mockResolvedValue({ items: [] })
    const result = await tenantAPIKeysService.listAPIKeys()
    expect(getMock).toHaveBeenCalledWith("/admin/security/api-keys")
    expect(result).toEqual({ items: [] })
  })

  it("creates API key with default scopes", async () => {
    postMock.mockResolvedValue({
      api_key: { id: "k1", name: "Test", scopes: ["agents.embed"], status: "active" },
      token: "tpk_secret_abc",
      token_type: "bearer",
    })

    const result = await tenantAPIKeysService.createAPIKey({ name: "Test" })

    expect(postMock).toHaveBeenCalledWith("/admin/security/api-keys", {
      name: "Test",
      scopes: ["agents.embed"],
    })
    expect(result.token).toBe("tpk_secret_abc")
    expect(result.api_key.name).toBe("Test")
  })

  it("creates API key with custom scopes", async () => {
    postMock.mockResolvedValue({
      api_key: { id: "k2", name: "Custom", scopes: ["agents.embed", "agents.read"], status: "active" },
      token: "tpk_secret_def",
      token_type: "bearer",
    })

    await tenantAPIKeysService.createAPIKey({ name: "Custom", scopes: ["agents.embed", "agents.read"] })

    expect(postMock).toHaveBeenCalledWith("/admin/security/api-keys", {
      name: "Custom",
      scopes: ["agents.embed", "agents.read"],
    })
  })

  it("revokes API key via POST /admin/security/api-keys/{key_id}/revoke", async () => {
    postMock.mockResolvedValue({
      api_key: { id: "k1", status: "revoked" },
    })

    const result = await tenantAPIKeysService.revokeAPIKey("k1")

    expect(postMock).toHaveBeenCalledWith("/admin/security/api-keys/k1/revoke")
    expect(result.api_key.status).toBe("revoked")
  })

  it("propagates errors from httpClient", async () => {
    getMock.mockRejectedValue(new Error("Unauthorized"))

    await expect(tenantAPIKeysService.listAPIKeys()).rejects.toThrow("Unauthorized")
  })
})
