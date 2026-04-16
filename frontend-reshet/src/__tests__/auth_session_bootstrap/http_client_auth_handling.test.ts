import { httpClient, HttpRequestError } from "@/services/http"
import { useAuthStore } from "@/lib/store/useAuthStore"

describe("http client auth handling", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: "user-1", role: "admin" } as any,
      activeOrganization: null,
      activeProject: null,
      organizations: [],
      projects: [],
      effectiveScopes: [],
      hydrated: true,
      sessionChecked: true,
    })
    jest.restoreAllMocks()
  })

  it("does not clear the auth store for generic 401 responses", async () => {
    Object.defineProperty(globalThis, "fetch", {
      value: jest.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Unauthorized" }),
        statusText: "Unauthorized",
      } as Response),
      configurable: true,
      writable: true,
    })

    await expect(httpClient.get("/some-protected-endpoint")).rejects.toBeInstanceOf(HttpRequestError)
    expect(useAuthStore.getState().user?.id).toBe("user-1")
  })
})
