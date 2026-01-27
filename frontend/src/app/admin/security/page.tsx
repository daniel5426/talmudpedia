"use client"

import React, { useState, useEffect, useCallback } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { useDirection } from "@/components/direction-provider"
import { cn } from "@/lib/utils"
import { rbacService, Role, RoleAssignment, Permission } from "@/services/rbac"
import { orgUnitsService, OrgUnit } from "@/services/org-units"
import {
  ShieldCheck,
  UserPlus,
  Plus,
  Trash2,
  Lock,
  Globe,
  User,
  MoreVertical,
  Key
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

  // Dialog states
  const [isRoleDialogOpen, setIsRoleDialogOpen] = useState(false)
  const [isAssignDialogOpen, setIsAssignDialogOpen] = useState(false)
  const [newRoleData, setNewRoleData] = useState<{ name: string; description: string; permissions: Permission[] }>({
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

  useEffect(() => {
    fetchData()
  }, [fetchData])

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

  if (!currentTenant) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Please select a tenant from the sidebar to manage security settings.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "Security & RBAC", active: true },
            ]} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="h-9" onClick={() => setIsRoleDialogOpen(true)}>
            <ShieldCheck className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> New Role
          </Button>
          <Button size="sm" className="h-9" onClick={() => setIsAssignDialogOpen(true)}>
            <UserPlus className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> Assign Role
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">

        <Tabs defaultValue="assignments" dir={direction}>
          <div className="flex items-center justify-between mb-4">
            <TabsList>
              <TabsTrigger value="assignments">Role Assignments</TabsTrigger>
              <TabsTrigger value="roles">Roles & Permissions</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="assignments">
            <Card>
              <CardHeader className={isRTL ? "text-right" : "text-left"}>
                <CardTitle className="text-lg">Active Assignments</CardTitle>
                <CardDescription>Users bound to roles at specific scopes.</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : assignments.length === 0 ? (
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
                      {assignments.map(a => (
                        <TableRow key={a.id}>
                          <TableCell className={cn("font-medium", isRTL ? "text-right" : "text-left")}>
                            <div className="flex items-center gap-2">
                              <User className="size-4 text-muted-foreground" />
                              <span>{a.user_id}</span> {/* In real app show email/name */}
                            </div>
                          </TableCell>
                          <TableCell className={isRTL ? "text-right" : "text-left"}>
                            <Badge variant="outline">{a.role_name}</Badge>
                          </TableCell>
                          <TableCell className={isRTL ? "text-right" : "text-left"}>
                            <div className="flex items-center gap-2">
                              {a.scope_type === "tenant" ? <Globe className="size-3" /> : <Lock className="size-3" />}
                              <span className="text-xs uppercase opacity-70">{a.scope_type}</span>
                              <span className="text-xs">{a.scope_id}</span>
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

          <TabsContent value="roles">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {isLoading ? (
                [1, 2, 3].map(i => <Skeleton key={i} className="h-48 w-full" />)
              ) : roles.map(role => (
                <Card key={role.id} className="relative overflow-hidden">
                  {role.is_system && (
                    <div className={cn(
                      "absolute top-0 p-1 bg-primary text-[8px] text-primary-foreground uppercase font-bold px-2",
                      isRTL ? "left-0 rounded-br-lg" : "right-0 rounded-bl-lg"
                    )}>
                      System
                    </div>
                  )}
                  <CardHeader className={cn("pb-2", isRTL ? "text-right" : "text-left")}>
                    <CardTitle className="text-base flex items-center justify-between">
                      {role.name}
                      {!role.is_system && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="size-6">
                              <MoreVertical className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align={isRTL ? "start" : "end"}>
                            <DropdownMenuItem className="text-destructive" onClick={() => handleDeleteRole(role.id)}>
                              <Trash2 className={cn("size-3", isRTL ? "ml-2" : "mr-2")} /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </CardTitle>
                    <CardDescription className="text-xs line-clamp-2">
                      {role.description || "No description provided."}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className={isRTL ? "text-right" : "text-left"}>
                    <div className={cn("flex flex-wrap gap-1", isRTL ? "justify-start" : "justify-start")}>
                      {role.permissions.slice(0, 6).map((p, i) => (
                        <Badge key={i} variant="secondary" className="text-[9px] px-1 py-0 h-4">
                          {p.resource_type}:{p.action}
                        </Badge>
                      ))}
                      {role.permissions.length > 6 && (
                        <Badge variant="secondary" className="text-[9px] px-1 py-0 h-4">
                          +{role.permissions.length - 6} more
                        </Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        {/* Role Creation Dialog */}
        <Dialog open={isRoleDialogOpen} onOpenChange={setIsRoleDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-auto">
            <DialogHeader>
              <DialogTitle>Create Custom Role</DialogTitle>
              <DialogDescription>Define a set of permissions for a new role.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="role-name">Role Name</Label>
                <Input
                  id="role-name"
                  placeholder="Content Editor"
                  value={newRoleData.name}
                  onChange={e => setNewRoleData({ ...newRoleData, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role-desc">Description</Label>
                <Input
                  id="role-desc"
                  placeholder="Can manage indices but not delete them"
                  value={newRoleData.description}
                  onChange={e => setNewRoleData({ ...newRoleData, description: e.target.value })}
                />
              </div>

              <div className="space-y-2 pt-4">
                <Label>Permissions Matrix</Label>
                <div className="border rounded-lg overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50">
                        <TableHead className="w-32">Resource</TableHead>
                        {ACTIONS.map(a => (
                          <TableHead key={a} className="text-center text-[10px] uppercase font-bold">{a}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {RESOURCE_TYPES.map(res => (
                        <TableRow key={res}>
                          <TableCell className="font-medium text-xs py-2 uppercase">{res}</TableCell>
                          {ACTIONS.map(action => (
                            <TableCell key={action} className="text-center py-2">
                              <Checkbox
                                checked={newRoleData.permissions.some(p => p.resource_type === res && p.action === action)}
                                onCheckedChange={() => togglePermission(res, action)}
                              />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsRoleDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleCreateRole} disabled={!newRoleData.name}>Create Role</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Assignment Dialog */}
        <Dialog open={isAssignDialogOpen} onOpenChange={setIsAssignDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Assign Role to User</DialogTitle>
              <DialogDescription>Grant a user permissions at a specific scope.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="assign-user">User ID</Label>
                <Input
                  id="assign-user"
                  placeholder="user_id..."
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
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="assign-scope-type">Scope Type</Label>
                  <select
                    id="assign-scope-type"
                    className="w-full h-10 px-3 rounded-md border border-input bg-background"
                    value={newAssignmentData.scope_type}
                    onChange={e => setNewAssignmentData({ ...newAssignmentData, scope_type: e.target.value })}
                  >
                    <option value="tenant">Entire Tenant</option>
                    <option value="org_unit">Organization Unit</option>
                    <option value="index">Specific Index</option>
                  </select>
                </div>
                {newAssignmentData.scope_type !== "tenant" && (
                  <div className="space-y-2">
                    <Label htmlFor="assign-scope-id">Scope Target</Label>
                    <select
                      id="assign-scope-id"
                      className="w-full h-10 px-3 rounded-md border border-input bg-background"
                      value={newAssignmentData.scope_id}
                      onChange={e => setNewAssignmentData({ ...newAssignmentData, scope_id: e.target.value })}
                    >
                      <option value="">Select target...</option>
                      {newAssignmentData.scope_type === "org_unit" && orgUnits.map(u => (
                        <option key={u.id} value={u.id}>{u.name} ({u.type})</option>
                      ))}
                      {/* For index we'd need to fetch indices too, or allow typing ID */}
                    </select>
                  </div>
                )}
              </div>
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
      </div>
    </div>
  )
}
