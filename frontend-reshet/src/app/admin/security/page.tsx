"use client"

import React, { useState, useEffect, useCallback, useMemo } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { rbacService, Role, RoleAssignment, Permission } from "@/services/rbac"
import { orgUnitsService, OrgUnit } from "@/services/org-units"
import {
  workloadSecurityService,
  PendingScopePolicy,
  ActionApprovalDecision,
} from "@/services/workload-security"
import {
  ShieldCheck,
  UserPlus,
  Trash2,
  Edit2,
  Lock,
  Globe,
  User,
  MoreVertical,
  Key,
  CheckCircle2,
  XCircle,
} from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Checkbox } from "@/components/ui/checkbox"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Textarea } from "@/components/ui/textarea"

const RESOURCE_TYPES = ["index", "pipeline", "job", "org_unit", "role", "membership", "audit"]
const ACTIONS = ["read", "write", "delete", "execute", "admin"]

export default function SecurityPage() {
  const { currentTenant } = useTenant()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [roles, setRoles] = useState<Role[]>([])
  const [assignments, setAssignments] = useState<RoleAssignment[]>([])
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isWorkloadLoading, setIsWorkloadLoading] = useState(true)
  const [searchRoles, setSearchRoles] = useState("")
  const [searchAssignments, setSearchAssignments] = useState("")
  const [searchWorkloads, setSearchWorkloads] = useState("")
  const [activeTab, setActiveTab] = useState<"assignments" | "roles" | "workloads">("assignments")
  const [pendingPolicies, setPendingPolicies] = useState<PendingScopePolicy[]>([])
  const [actionApprovals, setActionApprovals] = useState<ActionApprovalDecision[]>([])
  const [decisionForm, setDecisionForm] = useState({
    subject_type: "",
    subject_id: "",
    action_scope: "",
    rationale: "",
  })

  const [isRoleDialogOpen, setIsRoleDialogOpen] = useState(false)
  const [isAssignDialogOpen, setIsAssignDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [newRoleData, setNewRoleData] = useState<{ name: string; description: string; permissions: Permission[] }>({
    name: "",
    description: "",
    permissions: []
  })
  const [editRoleData, setEditRoleData] = useState<{ id: string; name: string; description: string; permissions: Permission[] }>({
    id: "",
    name: "",
    description: "",
    permissions: []
  })
  const [newAssignmentData, setNewAssignmentData] = useState({
    user_id: "",
    role_id: "",
    scope_id: "",
    scope_type: "org_unit"
  })

  const fetchData = useCallback(async () => {
    if (!currentTenant) return
    setIsLoading(true)
    try {
      const [rolesData, assignmentsData, unitsData] = await Promise.all([
        rbacService.listRoles(currentTenant.slug),
        rbacService.listRoleAssignments(currentTenant.slug),
        orgUnitsService.listOrgUnits(currentTenant.slug)
      ])
      setRoles(rolesData)
      setAssignments(assignmentsData)
      setOrgUnits(unitsData)
    } catch (error) {
      console.error("Failed to fetch security data", error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTenant])

  const fetchWorkloadData = useCallback(async () => {
    if (!currentTenant) return
    setIsWorkloadLoading(true)
    try {
      const [pendingData, approvalsData] = await Promise.all([
        workloadSecurityService.listPendingPolicies(),
        workloadSecurityService.listActionApprovals(),
      ])
      setPendingPolicies(pendingData)
      setActionApprovals(approvalsData)
    } catch (error) {
      console.error("Failed to fetch workload approvals data", error)
    } finally {
      setIsWorkloadLoading(false)
    }
  }, [currentTenant])

  useEffect(() => {
    fetchData()
    fetchWorkloadData()
  }, [fetchData, fetchWorkloadData])

  const handleCreateRole = async () => {
    if (!currentTenant) return
    try {
      await rbacService.createRole(currentTenant.slug, newRoleData)
      setIsRoleDialogOpen(false)
      setNewRoleData({ name: "", description: "", permissions: [] })
      fetchData()
    } catch (error) {
      console.error("Failed to create role", error)
    }
  }

  const handleAssignRole = async () => {
    if (!currentTenant) return
    try {
      await rbacService.createRoleAssignment(currentTenant.slug, newAssignmentData)
      setIsAssignDialogOpen(false)
      setNewAssignmentData({ user_id: "", role_id: "", scope_id: "", scope_type: "org_unit" })
      fetchData()
    } catch (error) {
      console.error("Failed to assign role", error)
    }
  }

  const handleEditRole = async () => {
    if (!currentTenant || !editRoleData.id) return
    try {
      await rbacService.updateRole(currentTenant.slug, editRoleData.id, {
        name: editRoleData.name,
        description: editRoleData.description,
        permissions: editRoleData.permissions
      })
      setIsEditDialogOpen(false)
      setEditRoleData({ id: "", name: "", description: "", permissions: [] })
      fetchData()
    } catch (error) {
      console.error("Failed to update role", error)
    }
  }

  const handleDeleteRole = async (roleId: string) => {
    if (!currentTenant || !confirm("Are you sure? Roles with active assignments cannot be deleted.")) return
    try {
      await rbacService.deleteRole(currentTenant.slug, roleId)
      fetchData()
    } catch (error) {
      console.error("Failed to delete role", error)
    }
  }

  const handleRevokeAssignment = async (assignmentId: string) => {
    if (!currentTenant || !confirm("Revoke this role assignment?")) return
    try {
      await rbacService.deleteRoleAssignment(currentTenant.slug, assignmentId)
      fetchData()
    } catch (error) {
      console.error("Failed to revoke assignment", error)
    }
  }

  const handleApprovePolicy = async (policy: PendingScopePolicy) => {
    if (!confirm("Approve this workload policy with all requested scopes?")) return
    try {
      await workloadSecurityService.approveScopePolicy(policy.principal_id, policy.requested_scopes || [])
      fetchWorkloadData()
    } catch (error) {
      console.error("Failed to approve workload policy", error)
    }
  }

  const handleRejectPolicy = async (principalId: string) => {
    if (!confirm("Reject this workload policy?")) return
    try {
      await workloadSecurityService.rejectScopePolicy(principalId)
      fetchWorkloadData()
    } catch (error) {
      console.error("Failed to reject workload policy", error)
    }
  }

  const handleDecideActionApproval = async (
    input: {
      subject_type: string
      subject_id: string
      action_scope: string
      rationale?: string
    },
    status: "approved" | "rejected"
  ) => {
    try {
      await workloadSecurityService.decideActionApproval({
        ...input,
        status,
      })
      fetchWorkloadData()
    } catch (error) {
      console.error("Failed to decide action approval", error)
    }
  }

  const togglePermission = (res: string, action: string) => {
    setNewRoleData(prev => {
      const exists = prev.permissions.some(p => p.resource_type === res && p.action === action)
      if (exists) {
        return {
          ...prev,
          permissions: prev.permissions.filter(p => !(p.resource_type === res && p.action === action))
        }
      } else {
        return {
          ...prev,
          permissions: [...prev.permissions, { resource_type: res, action: action }]
        }
      }
    })
  }

  const toggleEditPermission = (res: string, action: string) => {
    setEditRoleData(prev => {
      const exists = prev.permissions.some(p => p.resource_type === res && p.action === action)
      if (exists) {
        return {
          ...prev,
          permissions: prev.permissions.filter(p => !(p.resource_type === res && p.action === action))
        }
      } else {
        return {
          ...prev,
          permissions: [...prev.permissions, { resource_type: res, action: action }]
        }
      }
    })
  }

  const filteredRoles = useMemo(() => {
    const query = searchRoles.toLowerCase()
    if (!query) return roles
    return roles.filter(role =>
      role.name.toLowerCase().includes(query) ||
      (role.description || "").toLowerCase().includes(query)
    )
  }, [roles, searchRoles])

  const filteredAssignments = useMemo(() => {
    const query = searchAssignments.toLowerCase()
    if (!query) return assignments
    return assignments.filter(a =>
      a.user_id.toLowerCase().includes(query) ||
      a.role_name.toLowerCase().includes(query) ||
      (a.scope_type || "").toLowerCase().includes(query)
    )
  }, [assignments, searchAssignments])

  const filteredPendingPolicies = useMemo(() => {
    const query = searchWorkloads.toLowerCase().trim()
    if (!query) return pendingPolicies
    return pendingPolicies.filter((policy) => {
      const scopes = (policy.requested_scopes || []).join(" ").toLowerCase()
      return (
        policy.principal_id.toLowerCase().includes(query) ||
        policy.policy_id.toLowerCase().includes(query) ||
        scopes.includes(query)
      )
    })
  }, [pendingPolicies, searchWorkloads])

  const filteredActionApprovals = useMemo(() => {
    const query = searchWorkloads.toLowerCase().trim()
    if (!query) return actionApprovals
    return actionApprovals.filter((approval) => {
      return (
        approval.subject_type.toLowerCase().includes(query) ||
        approval.subject_id.toLowerCase().includes(query) ||
        approval.action_scope.toLowerCase().includes(query) ||
        approval.status.toLowerCase().includes(query)
      )
    })
  }, [actionApprovals, searchWorkloads])

  if (!currentTenant) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Please select a tenant from the sidebar to manage security settings.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <CustomBreadcrumb items={[
            { label: "Security & Org", href: "/admin/organization" },
            { label: "Security", active: true }
          ]} />
        </div>
        {activeTab !== "workloads" && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="h-9" onClick={() => setIsRoleDialogOpen(true)}>
              <ShieldCheck className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> New Role
            </Button>
            <Button size="sm" className="h-9" onClick={() => setIsAssignDialogOpen(true)}>
              <UserPlus className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> Assign Role
            </Button>
          </div>
        )}
      </header>

      <div className="flex-1 min-h-0 overflow-auto p-6 space-y-6">
        <Tabs
          defaultValue="assignments"
          dir={direction}
          className="min-h-0 h-full flex flex-col"
          onValueChange={(value) => setActiveTab(value as "assignments" | "roles" | "workloads")}
        >
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <TabsList>
              <TabsTrigger value="assignments">Role Assignments</TabsTrigger>
              <TabsTrigger value="roles">Roles & Permissions</TabsTrigger>
              <TabsTrigger value="workloads">Workload Approvals</TabsTrigger>
            </TabsList>
            {activeTab !== "workloads" ? (
              <Input
                placeholder={activeTab === "assignments" ? "Search user, role, or scope..." : "Search roles..."}
                value={activeTab === "assignments" ? searchAssignments : searchRoles}
                onChange={(e) => {
                  const value = e.target.value
                  if (activeTab === "assignments") setSearchAssignments(value)
                  else setSearchRoles(value)
                }}
                className="max-w-xs bg-background"
              />
            ) : (
              <Input
                placeholder="Search principal, policy, subject, or scope..."
                value={searchWorkloads}
                onChange={(e) => setSearchWorkloads(e.target.value)}
                className="max-w-xs bg-background"
              />
            )}
          </div>

          <TabsContent value="assignments" className="h-full flex-1 min-h-0 flex flex-col">
            <Card className="shadow-sm h-full flex flex-col">
              <CardContent className="flex-1">
                <div className="flex items-center justify-between mb-3">
                  <Badge variant="outline" className="text-xs">{filteredAssignments.length} results</Badge>
                </div>
                {isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : filteredAssignments.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                    No role assignments found.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>User</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Role</TableHead>
                        <TableHead className={isRTL ? "text-right" : "text-left"}>Scope</TableHead>
                        <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredAssignments.map(a => (
                        <TableRow key={a.id}>
                          <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                            <div className="flex items-center gap-2">
                              <div className="size-7 rounded-full bg-muted flex items-center justify-center">
                                <User className="size-3.5 text-muted-foreground" />
                              </div>
                              <span className="truncate max-w-[200px]">{a.user_id}</span>
                            </div>
                          </TableCell>
                          <TableCell className={isRTL ? "text-right" : "text-left"}>
                            <Badge variant="outline" className="text-xs">{a.role_name}</Badge>
                          </TableCell>
                          <TableCell className={isRTL ? "text-right" : "text-left"}>
                            <div className="flex items-center gap-2 text-xs">
                              {a.scope_type === "tenant" ? <Globe className="size-3" /> : <Lock className="size-3" />}
                              <span className="uppercase tracking-wide text-muted-foreground">{a.scope_type}</span>
                            </div>
                          </TableCell>
                          <TableCell className={isRTL ? "text-left" : "text-right"}>
                            <Button variant="ghost" size="icon" onClick={() => handleRevokeAssignment(a.id)}>
                              <Trash2 className="size-4 text-destructive" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="roles" className="h-full flex-1 min-h-0 flex flex-col">
            <div className="grid grid-cols-1 gap-6 min-h-0 h-full flex-1">
              <Card className="shadow-sm h-full flex flex-col">
                <CardContent className="flex-1">
                  <div className="flex items-center justify-between mb-3">
                    <Badge variant="outline" className="text-xs">{filteredRoles.length} roles</Badge>
                  </div>
                  {isLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-24 w-full" />
                      <Skeleton className="h-24 w-full" />
                    </div>
                  ) : filteredRoles.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                      No roles found.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {filteredRoles.map(role => (
                        <Card key={role.id} className="relative overflow-hidden">
                          {role.is_system && (
                            <div className="absolute top-3 right-3">
                              <Badge variant="secondary" className="gap-1"><Key className="size-3" /> System</Badge>
                            </div>
                          )}
                          <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                              <ShieldCheck className="size-4 text-primary" />
                              {role.name}
                            </CardTitle>
                            <CardDescription>
                              {role.description || "No description provided."}
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="space-y-3">
                            <div className="flex flex-wrap gap-2">
                              {role.permissions.slice(0, 6).map((p, i) => (
                                <Badge key={i} variant="outline" className="text-xs">
                                  {p.action}:{p.resource_type}
                                </Badge>
                              ))}
                              {role.permissions.length > 6 && (
                                <Badge variant="secondary" className="text-xs">+{role.permissions.length - 6} more</Badge>
                              )}
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-muted-foreground">{role.permissions.length} permissions</span>
                              {!role.is_system && (
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon">
                                      <MoreVertical className="size-4" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end">
                                    <DropdownMenuItem onClick={() => {
                                      setEditRoleData({
                                        id: role.id,
                                        name: role.name,
                                        description: role.description || "",
                                        permissions: role.permissions || []
                                      })
                                      setIsEditDialogOpen(true)
                                    }}>
                                      <Edit2 className="size-4 mr-2" /> Edit
                                    </DropdownMenuItem>
                                    <DropdownMenuItem className="text-destructive" onClick={() => handleDeleteRole(role.id)}>
                                      <Trash2 className="size-4 mr-2" /> Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

            </div>
          </TabsContent>

          <TabsContent value="workloads" className="h-full flex-1 min-h-0 flex flex-col">
            <div className="grid grid-cols-1 gap-6 min-h-0 h-full flex-1">
              <Card className="shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base">Pending Workload Scope Policies</CardTitle>
                  <CardDescription>
                    Approve or reject requested workload scopes for principals.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between mb-3">
                    <Badge variant="outline" className="text-xs">{filteredPendingPolicies.length} pending</Badge>
                  </div>
                  {isWorkloadLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : filteredPendingPolicies.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                      No pending workload scope policies.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Principal</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Requested Scopes</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Created</TableHead>
                          <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredPendingPolicies.map((policy) => (
                          <TableRow key={policy.policy_id}>
                            <TableCell className={cn("font-mono text-xs", isRTL ? "text-right" : "text-left")}>
                              {policy.principal_id}
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <div className="flex flex-wrap gap-1">
                                {(policy.requested_scopes || []).map((scope) => (
                                  <Badge key={scope} variant="secondary" className="text-[10px]">
                                    {scope}
                                  </Badge>
                                ))}
                              </div>
                            </TableCell>
                            <TableCell className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
                              {new Date(policy.created_at).toLocaleString()}
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                              <div className="flex items-center justify-end gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleApprovePolicy(policy)}
                                >
                                  <CheckCircle2 className="size-4 mr-2" />
                                  Approve Requested
                                </Button>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() => handleRejectPolicy(policy.principal_id)}
                                >
                                  <XCircle className="size-4 mr-2" />
                                  Reject
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>

              <Card className="shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base">Action Approvals</CardTitle>
                  <CardDescription>
                    Decide sensitive workload actions from one screen.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                    <Input
                      placeholder="subject_type (e.g. agent)"
                      value={decisionForm.subject_type}
                      onChange={(e) => setDecisionForm((prev) => ({ ...prev, subject_type: e.target.value }))}
                    />
                    <Input
                      placeholder="subject_id"
                      value={decisionForm.subject_id}
                      onChange={(e) => setDecisionForm((prev) => ({ ...prev, subject_id: e.target.value }))}
                    />
                    <Input
                      placeholder="action_scope (e.g. agents.publish)"
                      value={decisionForm.action_scope}
                      onChange={(e) => setDecisionForm((prev) => ({ ...prev, action_scope: e.target.value }))}
                    />
                    <div className="flex gap-2">
                      <Button
                        className="flex-1"
                        onClick={() => handleDecideActionApproval(decisionForm, "approved")}
                        disabled={!decisionForm.subject_type || !decisionForm.subject_id || !decisionForm.action_scope}
                      >
                        Approve
                      </Button>
                      <Button
                        className="flex-1"
                        variant="destructive"
                        onClick={() => handleDecideActionApproval(decisionForm, "rejected")}
                        disabled={!decisionForm.subject_type || !decisionForm.subject_id || !decisionForm.action_scope}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    placeholder="Optional rationale"
                    value={decisionForm.rationale}
                    onChange={(e) => setDecisionForm((prev) => ({ ...prev, rationale: e.target.value }))}
                  />

                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-xs">{filteredActionApprovals.length} decisions</Badge>
                  </div>
                  {isWorkloadLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : filteredActionApprovals.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                      No action approval decisions found.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Subject</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Action Scope</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Status</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Decided</TableHead>
                          <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredActionApprovals.map((approval) => (
                          <TableRow key={approval.id}>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <div className="text-xs">
                                <div className="font-medium">{approval.subject_type}</div>
                                <div className="font-mono text-muted-foreground">{approval.subject_id}</div>
                              </div>
                            </TableCell>
                            <TableCell className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
                              {approval.action_scope}
                            </TableCell>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <Badge
                                variant={
                                  approval.status === "approved"
                                    ? "default"
                                    : approval.status === "rejected"
                                      ? "destructive"
                                      : "secondary"
                                }
                                className="text-[10px]"
                              >
                                {approval.status}
                              </Badge>
                            </TableCell>
                            <TableCell className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
                              {approval.decided_at ? new Date(approval.decided_at).toLocaleString() : "n/a"}
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                              <div className="flex items-center justify-end gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    handleDecideActionApproval(
                                      {
                                        subject_type: approval.subject_type,
                                        subject_id: approval.subject_id,
                                        action_scope: approval.action_scope,
                                      },
                                      "approved"
                                    )
                                  }
                                >
                                  Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  onClick={() =>
                                    handleDecideActionApproval(
                                      {
                                        subject_type: approval.subject_type,
                                        subject_id: approval.subject_id,
                                        action_scope: approval.action_scope,
                                      },
                                      "rejected"
                                    )
                                  }
                                >
                                  Reject
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      <Dialog open={isRoleDialogOpen} onOpenChange={setIsRoleDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create New Role</DialogTitle>
            <DialogDescription>Define a set of permissions for a new role.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="role-name-modal">Role Name</Label>
              <Input
                id="role-name-modal"
                placeholder="Data Steward"
                value={newRoleData.name}
                onChange={e => setNewRoleData({ ...newRoleData, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role-desc-modal">Description</Label>
              <Input
                id="role-desc-modal"
                placeholder="Manage pipelines and audit logs"
                value={newRoleData.description}
                onChange={e => setNewRoleData({ ...newRoleData, description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Permissions</Label>
              <div className="grid grid-cols-1 gap-2 max-h-64 overflow-auto pr-1">
                {RESOURCE_TYPES.map(res => (
                  <div key={res} className="border rounded-lg p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{res}</div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {ACTIONS.map(action => (
                        <label key={`${res}-${action}`} className="flex items-center gap-2 text-xs">
                          <Checkbox
                            checked={newRoleData.permissions.some(p => p.resource_type === res && p.action === action)}
                            onCheckedChange={() => togglePermission(res, action)}
                          />
                          <span>{action}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsRoleDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateRole} disabled={!newRoleData.name}>Create Role</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isAssignDialogOpen} onOpenChange={setIsAssignDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign Role</DialogTitle>
            <DialogDescription>Assign a role to a user in a tenant or org unit scope.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="assign-user">User ID</Label>
              <Input
                id="assign-user"
                placeholder="User UUID"
                value={newAssignmentData.user_id}
                onChange={e => setNewAssignmentData({ ...newAssignmentData, user_id: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="assign-role">Role</Label>
              <select
                id="assign-role"
                className="w-full h-10 px-3 rounded-md border border-input bg-background"
                value={newAssignmentData.role_id}
                onChange={e => setNewAssignmentData({ ...newAssignmentData, role_id: e.target.value })}
              >
                <option value="">Select a role...</option>
                {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Scope</Label>
              <select
                className="w-full h-10 px-3 rounded-md border border-input bg-background"
                value={newAssignmentData.scope_type}
                onChange={e => setNewAssignmentData({ ...newAssignmentData, scope_type: e.target.value })}
              >
                <option value="tenant">Entire Tenant</option>
                <option value="org_unit">Organization Unit</option>
              </select>
            </div>
            {newAssignmentData.scope_type !== "tenant" && (
              <div className="space-y-2">
                <Label>Organization Unit</Label>
                <select
                  className="w-full h-10 px-3 rounded-md border border-input bg-background"
                  value={newAssignmentData.scope_id}
                  onChange={e => setNewAssignmentData({ ...newAssignmentData, scope_id: e.target.value })}
                >
                  <option value="">Select a unit...</option>
                  {orgUnits.map(u => (
                    <option key={u.id} value={u.id}>{u.name} ({u.type})</option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAssignDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={handleAssignRole}
              disabled={!newAssignmentData.user_id || !newAssignmentData.role_id || (newAssignmentData.scope_type !== "tenant" && !newAssignmentData.scope_id)}
            >
              Assign Role
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit Role</DialogTitle>
            <DialogDescription>Update role details and permissions.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-role-name">Role Name</Label>
              <Input
                id="edit-role-name"
                value={editRoleData.name}
                onChange={e => setEditRoleData({ ...editRoleData, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role-desc">Description</Label>
              <Input
                id="edit-role-desc"
                value={editRoleData.description}
                onChange={e => setEditRoleData({ ...editRoleData, description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Permissions</Label>
              <div className="grid grid-cols-1 gap-2 max-h-64 overflow-auto pr-1">
                {RESOURCE_TYPES.map(res => (
                  <div key={res} className="border rounded-lg p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{res}</div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {ACTIONS.map(action => (
                        <label key={`${res}-${action}`} className="flex items-center gap-2 text-xs">
                          <Checkbox
                            checked={editRoleData.permissions.some(p => p.resource_type === res && p.action === action)}
                            onCheckedChange={() => toggleEditPermission(res, action)}
                          />
                          <span>{action}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleEditRole} disabled={!editRoleData.name}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
