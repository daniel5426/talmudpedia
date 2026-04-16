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
})
