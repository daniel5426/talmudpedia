import { workloadSecurityService } from "@/services/workload-security"

const getMock = jest.fn()
const postMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}))

describe("workload security service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("lists pending policies", async () => {
    getMock.mockResolvedValue([])
    await workloadSecurityService.listPendingPolicies()
    expect(getMock).toHaveBeenCalledWith("/admin/security/workloads/pending")
  })

  it("submits approval decision payload", async () => {
    postMock.mockResolvedValue({ status: "approved" })
    await workloadSecurityService.decideActionApproval({
      subject_type: "agent",
      subject_id: "a1",
      action_scope: "agents.publish",
      status: "approved",
      rationale: "ok",
    })

    expect(postMock).toHaveBeenCalledWith("/admin/security/workloads/approvals/decide", {
      subject_type: "agent",
      subject_id: "a1",
      action_scope: "agents.publish",
      status: "approved",
      rationale: "ok",
    })
  })
})
