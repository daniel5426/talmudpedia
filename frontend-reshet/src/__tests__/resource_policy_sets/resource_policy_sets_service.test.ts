import { resourcePoliciesService } from "@/services/resource-policies"
import { resourcePoliciesService as barrelResourcePoliciesService } from "@/services"

const getMock = jest.fn()
const postMock = jest.fn()
const patchMock = jest.fn()
const putMock = jest.fn()
const deleteMock = jest.fn()

jest.mock("@/services/http", () => ({
  httpClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}))

describe("resource policy sets service", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("exports the shared service from the barrel", () => {
    expect(barrelResourcePoliciesService).toBe(resourcePoliciesService)
  })

  it("covers policy set CRUD and include endpoints", async () => {
    getMock.mockResolvedValue([{ id: "set-1" }])
    postMock.mockResolvedValue({ id: "set-1" })
    patchMock.mockResolvedValue({ id: "set-1", name: "Updated" })

    await resourcePoliciesService.listPolicySets()
    await resourcePoliciesService.getPolicySet("set-1")
    await resourcePoliciesService.createPolicySet({ name: "Alpha", is_active: true })
    await resourcePoliciesService.updatePolicySet("set-1", { name: "Updated" })
    await resourcePoliciesService.deletePolicySet("set-1")
    await resourcePoliciesService.addInclude("set-1", "set-2")
    await resourcePoliciesService.removeInclude("set-1", "set-2")

    expect(getMock).toHaveBeenNthCalledWith(1, "/admin/security/resource-policies/sets")
    expect(getMock).toHaveBeenNthCalledWith(2, "/admin/security/resource-policies/sets/set-1")
    expect(postMock).toHaveBeenNthCalledWith(1, "/admin/security/resource-policies/sets", {
      name: "Alpha",
      is_active: true,
    })
    expect(patchMock).toHaveBeenNthCalledWith(1, "/admin/security/resource-policies/sets/set-1", {
      name: "Updated",
    })
    expect(deleteMock).toHaveBeenNthCalledWith(1, "/admin/security/resource-policies/sets/set-1")
    expect(postMock).toHaveBeenNthCalledWith(2, "/admin/security/resource-policies/sets/set-1/includes", {
      included_policy_set_id: "set-2",
    })
    expect(deleteMock).toHaveBeenNthCalledWith(2, "/admin/security/resource-policies/sets/set-1/includes/set-2")
  })

  it("covers rule, assignment, and default policy endpoints", async () => {
    postMock.mockResolvedValue({ id: "rule-1" })
    patchMock.mockResolvedValue({ id: "rule-1" })
    putMock.mockResolvedValue({ id: "assignment-1" })

    await resourcePoliciesService.createRule("set-1", {
      resource_type: "model",
      resource_id: "model-1",
      rule_type: "quota",
      quota_unit: "tokens",
      quota_window: "monthly",
      quota_limit: 123,
    })
    await resourcePoliciesService.updateRule("rule-1", { quota_limit: 456 })
    await resourcePoliciesService.deleteRule("rule-1")
    await resourcePoliciesService.listAssignments()
    await resourcePoliciesService.upsertAssignment({
      principal_type: "embedded_external_user",
      policy_set_id: "set-1",
      embedded_agent_id: "agent-1",
      external_user_id: "external-1",
    })
    await resourcePoliciesService.deleteAssignment({
      principal_type: "embedded_external_user",
      embedded_agent_id: "agent-1",
      external_user_id: "external-1",
    })
    await resourcePoliciesService.setPublishedAppDefaultPolicy("app-1", "set-1")
    await resourcePoliciesService.setEmbeddedAgentDefaultPolicy("agent-1", null)

    expect(postMock).toHaveBeenCalledWith("/admin/security/resource-policies/sets/set-1/rules", {
      resource_type: "model",
      resource_id: "model-1",
      rule_type: "quota",
      quota_unit: "tokens",
      quota_window: "monthly",
      quota_limit: 123,
    })
    expect(patchMock).toHaveBeenCalledWith("/admin/security/resource-policies/rules/rule-1", {
      quota_limit: 456,
    })
    expect(deleteMock).toHaveBeenCalledWith("/admin/security/resource-policies/rules/rule-1")
    expect(getMock).toHaveBeenCalledWith("/admin/security/resource-policies/assignments")
    expect(putMock).toHaveBeenCalledWith("/admin/security/resource-policies/assignments", {
      principal_type: "embedded_external_user",
      policy_set_id: "set-1",
      embedded_agent_id: "agent-1",
      external_user_id: "external-1",
    })
    expect(deleteMock).toHaveBeenCalledWith(
      "/admin/security/resource-policies/assignments?principal_type=embedded_external_user&embedded_agent_id=agent-1&external_user_id=external-1"
    )
    expect(patchMock).toHaveBeenCalledWith(
      "/admin/security/resource-policies/published-apps/app-1/default-policy-set",
      { policy_set_id: "set-1" }
    )
    expect(patchMock).toHaveBeenCalledWith(
      "/admin/security/resource-policies/embedded-agents/agent-1/default-policy-set",
      { policy_set_id: null }
    )
  })

  it("propagates backend errors", async () => {
    postMock.mockRejectedValue(new Error("Policy set name already exists"))

    await expect(
      resourcePoliciesService.createPolicySet({ name: "Dup", is_active: true })
    ).rejects.toThrow("Policy set name already exists")
  })
})
