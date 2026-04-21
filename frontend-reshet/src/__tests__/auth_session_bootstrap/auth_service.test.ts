import { render, screen } from "@testing-library/react"
import React from "react"

import { OrganizationProvider, useOrganization } from "@/contexts/OrganizationContext"
import { useAuthStore } from "@/lib/store/useAuthStore"
import { authService } from "@/services/auth"
import { HttpRequestTimeoutError } from "@/services/http"

describe("auth session bootstrap service", () => {
  beforeEach(() => {
    jest.restoreAllMocks()
  })

  it("deduplicates concurrent getCurrentSession calls", async () => {
    const session = {
      user: { id: "user-1" },
      active_organization: { id: "org-1" },
      active_project: { id: "project-1" },
      organizations: [],
      projects: [],
      effective_scopes: [],
    } as any

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => session,
    } as Response)
    Object.defineProperty(globalThis, "fetch", {
      value: fetchMock,
      configurable: true,
      writable: true,
    })

    const [first, second] = await Promise.all([
      authService.getCurrentSession(),
      authService.getCurrentSession(),
    ])

    expect(first).toBe(session)
    expect(second).toBe(session)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("times out stalled getCurrentSession requests", async () => {
    jest.useFakeTimers()

    const fetchMock = jest.fn().mockImplementation((_input, init) => {
      const signal = init?.signal as AbortSignal
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        )
      })
    })
    Object.defineProperty(globalThis, "fetch", {
      value: fetchMock,
      configurable: true,
      writable: true,
    })

    const request = authService.getCurrentSession()

    jest.advanceTimersByTime(8000)

    await expect(request).rejects.toBeInstanceOf(HttpRequestTimeoutError)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    jest.useRealTimers()
  })

  it("treats canonical effective scopes as the only permission vocabulary", () => {
    useAuthStore.getState().setSession({
      authenticated: true,
      onboardingRequired: false,
      user: { id: "user-1", email: "user@example.com" },
      activeOrganization: { id: "org-1", name: "Org", status: "active" },
      activeProject: null,
      organizations: [],
      projects: [],
      effectiveScopes: ["organization_members.read"],
    })

    function Probe() {
      const { hasPermission } = useOrganization()
      return React.createElement(
        "div",
        null,
        React.createElement("span", { "data-testid": "canonical" }, String(hasPermission("organization_members", "read"))),
        React.createElement("span", { "data-testid": "legacy" }, String(hasPermission("membership", "read"))),
      )
    }

    render(React.createElement(OrganizationProvider, null, React.createElement(Probe)))

    expect(screen.getByTestId("canonical")).toHaveTextContent("true")
    expect(screen.getByTestId("legacy")).toHaveTextContent("false")
    useAuthStore.getState().clearSession()
  })
})
