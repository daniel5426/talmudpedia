import { httpClient } from "./http"

// ============================================================================
// Enums
// ============================================================================

export type ResourcePolicyPrincipalType =
  | "organization_user"
  | "published_app_account"
  | "embedded_external_user"

export type ResourcePolicyResourceType = "agent" | "tool" | "knowledge_store" | "model"

export type ResourcePolicyRuleType = "allow" | "quota"

export type ResourcePolicyQuotaUnit = "tokens"

export type ResourcePolicyQuotaWindow = "monthly"

// ============================================================================
// Response types
// ============================================================================

export interface ResourcePolicyRule {
  id: string
  resource_type: ResourcePolicyResourceType
  resource_id: string
  rule_type: ResourcePolicyRuleType
  quota_unit: ResourcePolicyQuotaUnit | null
  quota_window: ResourcePolicyQuotaWindow | null
  quota_limit: number | null
  created_at: string
  updated_at: string
}

export interface ResourcePolicySet {
  id: string
  name: string
  description: string | null
  is_active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
  included_policy_set_ids: string[]
  rules: ResourcePolicyRule[]
}

export interface ResourcePolicyAssignment {
  id: string
  principal_type: ResourcePolicyPrincipalType
  policy_set_id: string
  user_id: string | null
  published_app_account_id: string | null
  embedded_agent_id: string | null
  external_user_id: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

// ============================================================================
// Request types
// ============================================================================

export interface CreatePolicySetRequest {
  name: string
  description?: string
  is_active: boolean
}

export interface UpdatePolicySetRequest {
  name?: string
  description?: string
  is_active?: boolean
}

export interface CreatePolicyRuleRequest {
  resource_type: ResourcePolicyResourceType
  resource_id: string
  rule_type: ResourcePolicyRuleType
  quota_unit?: ResourcePolicyQuotaUnit
  quota_window?: ResourcePolicyQuotaWindow
  quota_limit?: number
}

export interface UpdatePolicyRuleRequest {
  resource_id?: string
  quota_unit?: ResourcePolicyQuotaUnit
  quota_window?: ResourcePolicyQuotaWindow
  quota_limit?: number
}

export interface UpsertAssignmentRequest {
  principal_type: ResourcePolicyPrincipalType
  policy_set_id: string
  user_id?: string
  published_app_account_id?: string
  embedded_agent_id?: string
  external_user_id?: string
}

export interface DeleteAssignmentParams {
  principal_type: ResourcePolicyPrincipalType
  user_id?: string
  published_app_account_id?: string
  embedded_agent_id?: string
  external_user_id?: string
}

// ============================================================================
// Service
// ============================================================================

const BASE = "/admin/security/resource-policies"

class ResourcePoliciesService {
  // ── Policy Sets ──

  async listPolicySets(): Promise<ResourcePolicySet[]> {
    return httpClient.get(`${BASE}/sets`)
  }

  async getPolicySet(id: string): Promise<ResourcePolicySet> {
    return httpClient.get(`${BASE}/sets/${id}`)
  }

  async createPolicySet(req: CreatePolicySetRequest): Promise<ResourcePolicySet> {
    return httpClient.post(`${BASE}/sets`, req)
  }

  async updatePolicySet(id: string, req: UpdatePolicySetRequest): Promise<ResourcePolicySet> {
    return httpClient.patch(`${BASE}/sets/${id}`, req)
  }

  async deletePolicySet(id: string): Promise<void> {
    return httpClient.delete(`${BASE}/sets/${id}`)
  }

  // ── Includes ──

  async addInclude(policySetId: string, includedPolicySetId: string): Promise<ResourcePolicySet> {
    return httpClient.post(`${BASE}/sets/${policySetId}/includes`, {
      included_policy_set_id: includedPolicySetId,
    })
  }

  async removeInclude(policySetId: string, includedPolicySetId: string): Promise<void> {
    return httpClient.delete(`${BASE}/sets/${policySetId}/includes/${includedPolicySetId}`)
  }

  // ── Rules ──

  async createRule(policySetId: string, req: CreatePolicyRuleRequest): Promise<ResourcePolicyRule> {
    return httpClient.post(`${BASE}/sets/${policySetId}/rules`, req)
  }

  async updateRule(ruleId: string, req: UpdatePolicyRuleRequest): Promise<ResourcePolicyRule> {
    return httpClient.patch(`${BASE}/rules/${ruleId}`, req)
  }

  async deleteRule(ruleId: string): Promise<void> {
    return httpClient.delete(`${BASE}/rules/${ruleId}`)
  }

  // ── Assignments ──

  async listAssignments(): Promise<ResourcePolicyAssignment[]> {
    return httpClient.get(`${BASE}/assignments`)
  }

  async upsertAssignment(req: UpsertAssignmentRequest): Promise<ResourcePolicyAssignment> {
    return httpClient.put(`${BASE}/assignments`, req)
  }

  async deleteAssignment(params: DeleteAssignmentParams): Promise<void> {
    const qs = new URLSearchParams()
    qs.set("principal_type", params.principal_type)
    if (params.user_id) qs.set("user_id", params.user_id)
    if (params.published_app_account_id) qs.set("published_app_account_id", params.published_app_account_id)
    if (params.embedded_agent_id) qs.set("embedded_agent_id", params.embedded_agent_id)
    if (params.external_user_id) qs.set("external_user_id", params.external_user_id)
    return httpClient.delete(`${BASE}/assignments?${qs.toString()}`)
  }

  // ── Default policy sets ──

  async setPublishedAppDefaultPolicy(publishedAppId: string, policySetId: string | null): Promise<void> {
    return httpClient.patch(`${BASE}/published-apps/${publishedAppId}/default-policy-set`, {
      policy_set_id: policySetId,
    })
  }

  async setEmbeddedAgentDefaultPolicy(agentId: string, policySetId: string | null): Promise<void> {
    return httpClient.patch(`${BASE}/embedded-agents/${agentId}/default-policy-set`, {
      policy_set_id: policySetId,
    })
  }
}

export const resourcePoliciesService = new ResourcePoliciesService()
