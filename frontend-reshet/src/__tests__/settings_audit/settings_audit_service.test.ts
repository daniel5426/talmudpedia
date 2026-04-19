import { settingsAuditService } from "@/services/settings-audit"

const getMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}))

describe("settings audit service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("loads audit list, count, and detail through the canonical settings endpoints", async () => {
    getMock.mockResolvedValue([])
    await settingsAuditService.listAuditLogs({ actor_email: "user@example.com", limit: 10 })
    await settingsAuditService.countAuditLogs({ actor_email: "user@example.com" })
    await settingsAuditService.getAuditLog("log-1")

    expect(getMock).toHaveBeenNthCalledWith(1, "/api/settings/audit-logs?actor_email=user%40example.com&limit=10")
    expect(getMock).toHaveBeenNthCalledWith(2, "/api/settings/audit-logs/count?actor_email=user%40example.com")
    expect(getMock).toHaveBeenNthCalledWith(3, "/api/settings/audit-logs/log-1")
  })
})
