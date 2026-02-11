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
  Search,
  ShieldAlert,
  Users,
  FileCheck,
  Clock,
} from "lucide-react"

import { Card } from "@/components/ui/card"
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
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Checkbox } from "@/components/ui/checkbox"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

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
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-3">
          <ShieldAlert className="h-10 w-10 mx-auto text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground/60">
            Please select a tenant from the sidebar to manage security settings.
          </p>
        </div>
      </div>
    )
  }

  const currentSearch = activeTab === "assignments" ? searchAssignments : activeTab === "roles" ? searchRoles : searchWorkloads
  const searchPlaceholder =
    activeTab === "assignments"
      ? "Search user, role, or scope..."
      : activeTab === "roles"
        ? "Search roles..."
        : "Search principal, policy, subject, or scope..."

  const handleSearchChange = (value: string) => {
    if (activeTab === "assignments") setSearchAssignments(value)
    else if (activeTab === "roles") setSearchRoles(value)
    else setSearchWorkloads(value)
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      {/* Header */}
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <CustomBreadcrumb items={[
          { label: "Security & Org", href: "/admin/organization" },
          { label: "Security", active: true }
        ]} />
        {activeTab !== "workloads" && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setIsRoleDialogOpen(true)}
            >
              <ShieldCheck className={cn("h-3.5 w-3.5", isRTL ? "ml-1.5" : "mr-1.5")} />
              New Role
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs"
              onClick={() => setIsAssignDialogOpen(true)}
            >
              <UserPlus className={cn("h-3.5 w-3.5", isRTL ? "ml-1.5" : "mr-1.5")} />
              Assign Role
            </Button>
          </div>
        )}
      </header>

      {/* Tabs + Content */}
      <Tabs
        defaultValue="assignments"
        value={activeTab}
        dir={direction}
        className="flex-1 min-h-0 flex flex-col"
        onValueChange={(value) => setActiveTab(value as "assignments" | "roles" | "workloads")}
      >
        <div className="border-b border-border/40 px-4 py-3 bg-background shrink-0 flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="assignments">
              <Users className={cn("h-3.5 w-3.5", isRTL ? "ml-1.5" : "mr-1.5")} />
              Assignments
            </TabsTrigger>
            <TabsTrigger value="roles">
              <ShieldCheck className={cn("h-3.5 w-3.5", isRTL ? "ml-1.5" : "mr-1.5")} />
              Roles
            </TabsTrigger>
            <TabsTrigger value="workloads">
              <FileCheck className={cn("h-3.5 w-3.5", isRTL ? "ml-1.5" : "mr-1.5")} />
              Workloads
            </TabsTrigger>
          </TabsList>

          <div className="relative w-full max-w-[240px]">
            <Search className={cn(
              "absolute top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50",
              isRTL ? "right-3" : "left-3"
            )} />
            <Input
              placeholder={searchPlaceholder}
              value={currentSearch}
              onChange={(e) => handleSearchChange(e.target.value)}
              className={cn("h-8 bg-muted/30 border-border/50 text-[13px]", isRTL ? "pr-9" : "pl-9")}
            />
          </div>
        </div>

        {/* =================== ASSIGNMENTS TAB =================== */}
        <TabsContent value="assignments" className="flex-1 min-h-0 overflow-auto mt-0 p-4">
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-3 w-16" />
                </div>
              ))}
            </div>
          ) : filteredAssignments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="rounded-xl border-2 border-dashed border-border/50 p-4 mb-4">
                <Users className="h-6 w-6 text-muted-foreground/40" />
              </div>
              <p className="text-sm font-medium text-muted-foreground/60">No role assignments found</p>
              <p className="text-xs text-muted-foreground/40 mt-1">Assign a role to a user to get started</p>
            </div>
          ) : (
            <div className="space-y-px">
              <div className="px-4 pb-2">
                <span className="text-[11px] font-medium text-muted-foreground/50 uppercase tracking-wider">
                  {filteredAssignments.length} assignment{filteredAssignments.length !== 1 ? "s" : ""}
                </span>
              </div>
              {filteredAssignments.map(a => (
                <div
                  key={a.id}
                  className="group flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-muted/40 transition-colors"
                >
                  {/* Avatar */}
                  <div className="h-8 w-8 rounded-full bg-muted/60 flex items-center justify-center shrink-0">
                    <User className="h-3.5 w-3.5 text-muted-foreground/60" />
                  </div>

                  {/* User + Role */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{a.user_id}</div>
                    <div className="text-xs text-muted-foreground/50">{a.role_name}</div>
                  </div>

                  {/* Scope */}
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground/50 shrink-0">
                    {a.scope_type === "tenant" ? (
                      <Globe className="h-3 w-3" />
                    ) : (
                      <Lock className="h-3 w-3" />
                    )}
                    <span className="uppercase tracking-wide">{a.scope_type}</span>
                  </div>

                  {/* Revoke */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                    onClick={() => handleRevokeAssignment(a.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* =================== ROLES TAB =================== */}
        <TabsContent value="roles" className="flex-1 min-h-0 overflow-auto mt-0 p-4">
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="rounded-xl border border-border/50 shadow-xs bg-card p-5 space-y-3">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                  <div className="pt-2">
                    <Skeleton className="h-3 w-20" />
                  </div>
                </div>
              ))}
            </div>
          ) : filteredRoles.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="rounded-xl border-2 border-dashed border-border/50 p-4 mb-4">
                <ShieldCheck className="h-6 w-6 text-muted-foreground/40" />
              </div>
              <p className="text-sm font-medium text-muted-foreground/60">No roles found</p>
              <p className="text-xs text-muted-foreground/40 mt-1">Create a role to define permission sets</p>
            </div>
          ) : (
            <>
              <div className="px-1 pb-3">
                <span className="text-[11px] font-medium text-muted-foreground/50 uppercase tracking-wider">
                  {filteredRoles.length} role{filteredRoles.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredRoles.map(role => (
                  <div
                    key={role.id}
                    className="group rounded-xl border border-border/50 shadow-xs bg-card p-5 transition-colors hover:bg-muted/30"
                  >
                    {/* Top: Icon + System badge + Menu */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                        <ShieldCheck className="h-4 w-4 text-primary" />
                      </div>
                      <div className="flex items-center gap-1.5">
                        {role.is_system && (
                          <Badge variant="secondary" className="text-[10px] gap-1 h-5 px-1.5">
                            <Key className="h-2.5 w-2.5" />
                            System
                          </Badge>
                        )}
                        {!role.is_system && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                              >
                                <MoreVertical className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align={isRTL ? "start" : "end"} className="w-36">
                              <DropdownMenuItem
                                className="text-xs"
                                onClick={() => {
                                  setEditRoleData({
                                    id: role.id,
                                    name: role.name,
                                    description: role.description || "",
                                    permissions: role.permissions || []
                                  })
                                  setIsEditDialogOpen(true)
                                }}
                              >
                                <Edit2 className={cn("h-3.5 w-3.5", isRTL ? "ml-2" : "mr-2")} />
                                Edit
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                className="text-xs text-destructive"
                                onClick={() => handleDeleteRole(role.id)}
                              >
                                <Trash2 className={cn("h-3.5 w-3.5", isRTL ? "ml-2" : "mr-2")} />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </div>

                    {/* Name + Description */}
                    <h3 className="text-sm font-semibold mb-1">{role.name}</h3>
                    <p className="text-xs text-muted-foreground/50 line-clamp-2 mb-4">
                      {role.description || "No description provided."}
                    </p>

                    {/* Footer: Permission count */}
                    <div className="flex items-center justify-between pt-3 border-t border-border/40">
                      <span className="text-[11px] text-muted-foreground/40">
                        {role.permissions.length} permission{role.permissions.length !== 1 ? "s" : ""}
                      </span>
                      {role.permissions.length > 0 && (
                        <div className="flex items-center gap-1">
                          {role.permissions.slice(0, 3).map((p, i) => (
                            <span
                              key={i}
                              className="inline-block h-1.5 w-1.5 rounded-full bg-primary/40"
                            />
                          ))}
                          {role.permissions.length > 3 && (
                            <span className="text-[10px] text-muted-foreground/40">
                              +{role.permissions.length - 3}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </TabsContent>

        {/* =================== WORKLOADS TAB =================== */}
        <TabsContent value="workloads" className="flex-1 min-h-0 overflow-auto mt-0 p-4 space-y-6">
          {/* Pending Policies Section */}
          <div>
            <div className="flex items-center gap-2 mb-3 px-1">
              <Clock className="h-3.5 w-3.5 text-muted-foreground/50" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/60">
                Pending Scope Policies
              </h2>
              <span className="text-[10px] text-muted-foreground/40 bg-muted/40 rounded-full px-2 py-0.5">
                {filteredPendingPolicies.length}
              </span>
            </div>

            {isWorkloadLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-border/50 shadow-xs bg-card">
                    <Skeleton className="h-4 w-28" />
                    <div className="flex-1"><Skeleton className="h-3 w-40" /></div>
                    <Skeleton className="h-7 w-16" />
                    <Skeleton className="h-7 w-16" />
                  </div>
                ))}
              </div>
            ) : filteredPendingPolicies.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14">
                <div className="rounded-xl border-2 border-dashed border-border/50 p-4 mb-4">
                  <FileCheck className="h-6 w-6 text-muted-foreground/40" />
                </div>
                <p className="text-sm font-medium text-muted-foreground/60">No pending policies</p>
                <p className="text-xs text-muted-foreground/40 mt-1">All workload scope policies have been reviewed</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {filteredPendingPolicies.map((policy) => (
                  <div
                    key={policy.policy_id}
                    className="group flex items-center gap-4 px-4 py-3 rounded-lg border border-border/50 shadow-xs bg-card hover:bg-muted/30 transition-colors"
                  >
                    {/* Principal */}
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-mono font-medium truncate">{policy.principal_id}</div>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {(policy.requested_scopes || []).map((scope) => (
                          <Badge key={scope} variant="secondary" className="text-[10px] h-5 px-1.5 font-mono">
                            {scope}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Created */}
                    <span className="text-[11px] text-muted-foreground/40 shrink-0 hidden sm:block">
                      {new Date(policy.created_at).toLocaleDateString()}
                    </span>

                    {/* Actions */}
                    <div className={cn("flex items-center gap-1.5 shrink-0", isRTL ? "flex-row-reverse" : "")}>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1"
                        onClick={() => handleApprovePolicy(policy)}
                      >
                        <CheckCircle2 className="h-3 w-3" />
                        Approve
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-destructive hover:text-destructive gap-1"
                        onClick={() => handleRejectPolicy(policy.principal_id)}
                      >
                        <XCircle className="h-3 w-3" />
                        Reject
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Action Approvals Section */}
          <div>
            <div className="flex items-center gap-2 mb-3 px-1">
              <ShieldAlert className="h-3.5 w-3.5 text-muted-foreground/50" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/60">
                Action Approvals
              </h2>
              <span className="text-[10px] text-muted-foreground/40 bg-muted/40 rounded-full px-2 py-0.5">
                {filteredActionApprovals.length}
              </span>
            </div>

            {/* Decision form */}
            <Card className="rounded-xl shadow-xs p-4 mb-4">
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Subject Type</Label>
                  <Input
                    placeholder="e.g. agent"
                    className="h-9 text-sm"
                    value={decisionForm.subject_type}
                    onChange={(e) => setDecisionForm((prev) => ({ ...prev, subject_type: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Subject ID</Label>
                  <Input
                    placeholder="Subject identifier"
                    className="h-9 text-sm"
                    value={decisionForm.subject_id}
                    onChange={(e) => setDecisionForm((prev) => ({ ...prev, subject_id: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">Action Scope</Label>
                  <Input
                    placeholder="e.g. agents.publish"
                    className="h-9 text-sm"
                    value={decisionForm.action_scope}
                    onChange={(e) => setDecisionForm((prev) => ({ ...prev, action_scope: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-muted-foreground">&nbsp;</Label>
                  <div className="flex gap-1.5">
                    <Button
                      size="sm"
                      className="flex-1 h-9 text-xs"
                      onClick={() => handleDecideActionApproval(decisionForm, "approved")}
                      disabled={!decisionForm.subject_type || !decisionForm.subject_id || !decisionForm.action_scope}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 h-9 text-xs text-destructive hover:text-destructive"
                      onClick={() => handleDecideActionApproval(decisionForm, "rejected")}
                      disabled={!decisionForm.subject_type || !decisionForm.subject_id || !decisionForm.action_scope}
                    >
                      Reject
                    </Button>
                  </div>
                </div>
              </div>
              <Textarea
                placeholder="Optional rationale..."
                className="mt-3 text-sm resize-none"
                rows={2}
                value={decisionForm.rationale}
                onChange={(e) => setDecisionForm((prev) => ({ ...prev, rationale: e.target.value }))}
              />
            </Card>

            {/* Action approvals list */}
            {isWorkloadLoading ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-border/50 shadow-xs bg-card">
                    <Skeleton className="h-4 w-20" />
                    <div className="flex-1"><Skeleton className="h-3 w-32" /></div>
                    <Skeleton className="h-5 w-14 rounded-full" />
                    <Skeleton className="h-7 w-16" />
                  </div>
                ))}
              </div>
            ) : filteredActionApprovals.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-14">
                <div className="rounded-xl border-2 border-dashed border-border/50 p-4 mb-4">
                  <ShieldAlert className="h-6 w-6 text-muted-foreground/40" />
                </div>
                <p className="text-sm font-medium text-muted-foreground/60">No action approval decisions</p>
                <p className="text-xs text-muted-foreground/40 mt-1">Use the form above to decide on action approvals</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {filteredActionApprovals.map((approval) => (
                  <div
                    key={approval.id}
                    className="group flex items-center gap-4 px-4 py-3 rounded-lg border border-border/50 bg-card hover:bg-muted/30 transition-colors"
                  >
                    {/* Subject info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">{approval.subject_type}</span>
                        <span className="text-[10px] text-muted-foreground/40">/</span>
                        <span className="text-xs font-mono text-muted-foreground/60 truncate">
                          {approval.subject_id}
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground/40 mt-0.5">{approval.action_scope}</div>
                    </div>

                    {/* Status dot */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          approval.status === "approved" && "bg-emerald-500",
                          approval.status === "rejected" && "bg-destructive",
                          approval.status === "pending" && "bg-amber-500"
                        )}
                      />
                      <span className="text-[11px] text-muted-foreground/50 capitalize">{approval.status}</span>
                    </div>

                    {/* Decided timestamp */}
                    <span className="text-[11px] text-muted-foreground/40 shrink-0 hidden sm:block">
                      {approval.decided_at ? new Date(approval.decided_at).toLocaleDateString() : "Pending"}
                    </span>

                    {/* Actions */}
                    <div className={cn(
                      "flex items-center gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity",
                      isRTL ? "flex-row-reverse" : ""
                    )}>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
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
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-destructive hover:text-destructive"
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
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* =================== CREATE ROLE DIALOG =================== */}
      <Dialog open={isRoleDialogOpen} onOpenChange={setIsRoleDialogOpen}>
        <DialogContent className="sm:max-w-2xl" dir={direction}>
          <DialogHeader>
            <DialogTitle className={cn("text-base", isRTL ? "text-right" : "text-left")}>
              Create New Role
            </DialogTitle>
            <DialogDescription className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
              Define a set of permissions for a new role.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="role-name-modal" className="text-xs font-medium text-muted-foreground">
                Role Name
              </Label>
              <Input
                id="role-name-modal"
                placeholder="Data Steward"
                className="h-9"
                value={newRoleData.name}
                onChange={e => setNewRoleData({ ...newRoleData, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role-desc-modal" className="text-xs font-medium text-muted-foreground">
                Description
              </Label>
              <Input
                id="role-desc-modal"
                placeholder="Manage pipelines and audit logs"
                className="h-9"
                value={newRoleData.description}
                onChange={e => setNewRoleData({ ...newRoleData, description: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Permissions</Label>
              <div className="grid grid-cols-1 gap-2 max-h-64 overflow-auto pr-1">
                {RESOURCE_TYPES.map(res => (
                  <div key={res} className="rounded-lg border border-border/50 p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">
                      {res}
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                      {ACTIONS.map(action => (
                        <label key={`${res}-${action}`} className="flex items-center gap-1.5 text-xs cursor-pointer">
                          <Checkbox
                            checked={newRoleData.permissions.some(p => p.resource_type === res && p.action === action)}
                            onCheckedChange={() => togglePermission(res, action)}
                          />
                          <span className="text-muted-foreground">{action}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" className="h-8" onClick={() => setIsRoleDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" className="h-8" onClick={handleCreateRole} disabled={!newRoleData.name}>
              Create Role
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* =================== ASSIGN ROLE DIALOG =================== */}
      <Dialog open={isAssignDialogOpen} onOpenChange={setIsAssignDialogOpen}>
        <DialogContent className="sm:max-w-[480px]" dir={direction}>
          <DialogHeader>
            <DialogTitle className={cn("text-base", isRTL ? "text-right" : "text-left")}>
              Assign Role
            </DialogTitle>
            <DialogDescription className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
              Assign a role to a user in a tenant or org unit scope.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="assign-user" className="text-xs font-medium text-muted-foreground">
                User ID
              </Label>
              <Input
                id="assign-user"
                placeholder="User UUID"
                className="h-9"
                value={newAssignmentData.user_id}
                onChange={e => setNewAssignmentData({ ...newAssignmentData, user_id: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="assign-role" className="text-xs font-medium text-muted-foreground">
                Role
              </Label>
              <Select
                value={newAssignmentData.role_id}
                onValueChange={(value) => setNewAssignmentData({ ...newAssignmentData, role_id: value })}
              >
                <SelectTrigger className="w-full h-9">
                  <SelectValue placeholder="Select a role..." />
                </SelectTrigger>
                <SelectContent>
                  {roles.map(r => (
                    <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Scope</Label>
              <Select
                value={newAssignmentData.scope_type}
                onValueChange={(value) => setNewAssignmentData({ ...newAssignmentData, scope_type: value })}
              >
                <SelectTrigger className="w-full h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tenant">Entire Tenant</SelectItem>
                  <SelectItem value="org_unit">Organization Unit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {newAssignmentData.scope_type !== "tenant" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Organization Unit</Label>
                <Select
                  value={newAssignmentData.scope_id}
                  onValueChange={(value) => setNewAssignmentData({ ...newAssignmentData, scope_id: value })}
                >
                  <SelectTrigger className="w-full h-9">
                    <SelectValue placeholder="Select a unit..." />
                  </SelectTrigger>
                  <SelectContent>
                    {orgUnits.map(u => (
                      <SelectItem key={u.id} value={u.id}>
                        {u.name} ({u.type})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" className="h-8" onClick={() => setIsAssignDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="h-8"
              onClick={handleAssignRole}
              disabled={!newAssignmentData.user_id || !newAssignmentData.role_id || (newAssignmentData.scope_type !== "tenant" && !newAssignmentData.scope_id)}
            >
              Assign Role
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* =================== EDIT ROLE DIALOG =================== */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-2xl" dir={direction}>
          <DialogHeader>
            <DialogTitle className={cn("text-base", isRTL ? "text-right" : "text-left")}>
              Edit Role
            </DialogTitle>
            <DialogDescription className={cn("text-xs", isRTL ? "text-right" : "text-left")}>
              Update role details and permissions.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="edit-role-name" className="text-xs font-medium text-muted-foreground">
                Role Name
              </Label>
              <Input
                id="edit-role-name"
                className="h-9"
                value={editRoleData.name}
                onChange={e => setEditRoleData({ ...editRoleData, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-role-desc" className="text-xs font-medium text-muted-foreground">
                Description
              </Label>
              <Input
                id="edit-role-desc"
                className="h-9"
                value={editRoleData.description}
                onChange={e => setEditRoleData({ ...editRoleData, description: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Permissions</Label>
              <div className="grid grid-cols-1 gap-2 max-h-64 overflow-auto pr-1">
                {RESOURCE_TYPES.map(res => (
                  <div key={res} className="rounded-lg border border-border/50 p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60 mb-2">
                      {res}
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                      {ACTIONS.map(action => (
                        <label key={`${res}-${action}`} className="flex items-center gap-1.5 text-xs cursor-pointer">
                          <Checkbox
                            checked={editRoleData.permissions.some(p => p.resource_type === res && p.action === action)}
                            onCheckedChange={() => toggleEditPermission(res, action)}
                          />
                          <span className="text-muted-foreground">{action}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" className="h-8" onClick={() => setIsEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" className="h-8" onClick={handleEditRole} disabled={!editRoleData.name}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
