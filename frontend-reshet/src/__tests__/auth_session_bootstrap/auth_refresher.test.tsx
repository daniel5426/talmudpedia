import { render, waitFor } from "@testing-library/react"

import { AuthRefresher } from "@/components/auth-refresher"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService, navigateToAuthRedirect } from "@/services/auth"
import { HttpRequestTimeoutError } from "@/services/http"

jest.mock("@/services/auth", () => {
  const actual = jest.requireActual("@/services/auth")
  return {
    ...actual,
    navigateToAuthRedirect: jest.fn(),
  }
})

describe("AuthRefresher", () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      user: { id: "user-1", role: "admin" } as any,
      activeOrganization: { id: "org-1", name: "Org 1", status: "active" } as any,
      activeProject: { id: "project-1", name: "Project 1", organization_id: "org-1", status: "active", is_default: true } as any,
      organizations: [],
      projects: [],
      effectiveScopes: ["*"],
      hydrated: true,
      sessionChecked: false,
    })
    jest.restoreAllMocks()
    ;(navigateToAuthRedirect as jest.Mock).mockReset()
  })

  it("keeps the current auth state and marks the session checked after a timeout", async () => {
    jest
      .spyOn(authService, "getCurrentSession")
      .mockRejectedValue(new HttpRequestTimeoutError("timeout", 8000))

    render(<AuthRefresher />)

    await waitFor(() => {
      const state = useAuthStore.getState()
      expect(state.sessionChecked).toBe(true)
      expect(state.user?.id).toBe("user-1")
    })
  })

  it("redirects through the browser when session bootstrap returns a redirect_url", async () => {
    jest.spyOn(authService, "getCurrentSession").mockResolvedValue({
      redirect_url: "https://example.com/workos/select-org",
    } as any)

    render(<AuthRefresher />)

    await waitFor(() => {
      expect(navigateToAuthRedirect).toHaveBeenCalledWith("https://example.com/workos/select-org")
      expect(useAuthStore.getState().sessionChecked).toBe(true)
    })
  })
})
