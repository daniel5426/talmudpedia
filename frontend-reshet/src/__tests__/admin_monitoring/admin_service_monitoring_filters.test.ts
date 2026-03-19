import { adminService } from "@/services/admin"

const getMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}))

describe("admin monitoring service filters", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    getMock.mockResolvedValue({})
  })

  it("sends actor and agent filters for users", async () => {
    await adminService.getUsers(2, 25, "alice", {
      actorType: "published_app_account",
      agentId: "agent-1",
      appId: "app-1",
    })

    expect(getMock).toHaveBeenCalledWith(
      "/admin/users?skip=25&limit=25&search=alice&actor_type=published_app_account&agent_id=agent-1&app_id=app-1",
    )
  })

  it("sends actor, surface, and agent filters for threads", async () => {
    await adminService.getThreads(1, 20, "embed", {
      actorType: "embedded_external_user",
      surface: "embedded_runtime",
      agentId: "agent-2",
    })

    expect(getMock).toHaveBeenCalledWith(
      "/admin/threads?skip=0&limit=20&search=embed&actor_type=embedded_external_user&surface=embedded_runtime&agent_id=agent-2",
    )
  })

  it("sends agent scope to summary stats", async () => {
    await adminService.getStatsSummary("agents", 7, "2026-03-01", "2026-03-19", { agentId: "agent-3" })

    expect(getMock).toHaveBeenCalledWith(
      "/admin/stats/summary?section=agents&days=7&start_date=2026-03-01&end_date=2026-03-19&agent_id=agent-3",
    )
  })
})
