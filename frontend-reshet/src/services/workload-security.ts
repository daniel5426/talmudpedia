import { httpClient } from "./http"

export type ApprovalStatus = "pending" | "approved" | "rejected"

export interface PendingScopePolicy {
  policy_id: string
  principal_id: string
  requested_scopes: string[]
  status: ApprovalStatus
  version: number
  created_at: string
}

export interface ScopePolicyApprovalResult {
  status: "approved"
  principal_id: string
  policy_id: string
  approved_scopes: string[]
  approved_at: string
}

export interface ScopePolicyRejectResult {
  status: "rejected"
  principal_id: string
  policy_id: string
}

export interface ActionApprovalDecision {
  id: string
  tenant_id?: string
  subject_type: string
  subject_id: string
  action_scope: string
  status: ApprovalStatus
  decided_by?: string | null
  rationale?: string | null
  created_at?: string
  decided_at?: string | null
}

class WorkloadSecurityService {
  async listPendingPolicies(): Promise<PendingScopePolicy[]> {
    return httpClient.get("/admin/security/workloads/pending")
  }

  async approveScopePolicy(
    principalId: string,
    approvedScopes: string[]
  ): Promise<ScopePolicyApprovalResult> {
    return httpClient.post(`/admin/security/workloads/principals/${principalId}/approve`, {
      approved_scopes: approvedScopes,
    })
  }

  async rejectScopePolicy(principalId: string): Promise<ScopePolicyRejectResult> {
    return httpClient.post(`/admin/security/workloads/principals/${principalId}/reject`)
  }

  async listActionApprovals(filters?: {
    subject_type?: string
    subject_id?: string
    action_scope?: string
  }): Promise<ActionApprovalDecision[]> {
    const params = new URLSearchParams()
    if (filters?.subject_type) params.set("subject_type", filters.subject_type)
    if (filters?.subject_id) params.set("subject_id", filters.subject_id)
    if (filters?.action_scope) params.set("action_scope", filters.action_scope)
    const query = params.toString() ? `?${params.toString()}` : ""
    return httpClient.get(`/admin/security/workloads/approvals${query}`)
  }

  async decideActionApproval(input: {
    subject_type: string
    subject_id: string
    action_scope: string
    status: Extract<ApprovalStatus, "approved" | "rejected">
    rationale?: string
  }): Promise<ActionApprovalDecision> {
    return httpClient.post("/admin/security/workloads/approvals/decide", input)
  }
}

export const workloadSecurityService = new WorkloadSecurityService()
