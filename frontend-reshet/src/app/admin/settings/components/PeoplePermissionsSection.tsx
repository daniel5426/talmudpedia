"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertCircle,
  Loader2,
  Plus,
  Trash2,
  UserPlus,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SearchInput } from "@/components/ui/search-input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatHttpErrorMessage } from "@/services/http"
import {
  settingsPeoplePermissionsService,
  settingsProjectsService,
  SettingsGroup,
  SettingsInvitation,
  SettingsMember,
  SettingsProject,
  SettingsRole,
  SettingsRoleAssignment,
} from "@/services"
import { MemberRoleAssignmentsDialog } from "@/app/admin/settings/components/MemberRoleAssignmentsDialog"
import { RoleFormState, RolePermissionDialog } from "@/app/admin/settings/components/RolePermissionDialog"
import { useOrganization } from "@/contexts/OrganizationContext"

function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function PeoplePermissionsSection() {
  const { currentOrganization } = useOrganization()
  const [activeTab, setActiveTab] = useState("members")
  const [members, setMembers] = useState<SettingsMember[]>([])
  const [invitations, setInvitations] = useState<SettingsInvitation[]>([])
  const [groups, setGroups] = useState<SettingsGroup[]>([])
  const [roles, setRoles] = useState<SettingsRole[]>([])
  const [assignments, setAssignments] = useState<SettingsRoleAssignment[]>([])
  const [projects, setProjects] = useState<SettingsProject[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")

  // Modal states
  const [inviteOpen, setInviteOpen] = useState(false)
  const [groupOpen, setGroupOpen] = useState(false)
  const [memberRoleOpen, setMemberRoleOpen] = useState(false)
  const [roleOpen, setRoleOpen] = useState(false)

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteProjectId, setInviteProjectId] = useState<string>("")
  const [inviteProjectRoleId, setInviteProjectRoleId] = useState<string>("")
  const [inviteSaving, setInviteSaving] = useState(false)

  // Group form
  const [groupForm, setGroupForm] = useState({ name: "", type: "team", parent_id: "" })
  const [groupSaving, setGroupSaving] = useState(false)

  // Member role assignment
  const [memberRoleTarget, setMemberRoleTarget] = useState<SettingsMember | null>(null)
  const [memberRoleId, setMemberRoleId] = useState("")
  const [memberProjectAccessRows, setMemberProjectAccessRows] = useState<Array<{ assignmentId?: string; projectId: string; roleId: string }>>([])
  const [memberRoleSaving, setMemberRoleSaving] = useState(false)

  // Custom role editor
  const [roleForm, setRoleForm] = useState<RoleFormState>({
    id: "",
    family: "",
    name: "",
    description: "",
    permissions: [],
  })
  const [roleSaving, setRoleSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [memberData, invitationData, groupData, roleData, assignmentData, projectData] = await Promise.all([
        settingsPeoplePermissionsService.listMembers(),
        settingsPeoplePermissionsService.listInvitations(),
        settingsPeoplePermissionsService.listGroups(),
        settingsPeoplePermissionsService.listRoles(),
        settingsPeoplePermissionsService.listRoleAssignments(),
        settingsProjectsService.listProjects(),
      ])
      setMembers(memberData)
      setInvitations(invitationData)
      setGroups(groupData)
      setRoles(roleData)
      setAssignments(assignmentData)
      setProjects(projectData)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to load people and permissions."))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  // ── Filtered data ──
  const filteredMembers = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return members
    return members.filter(
      (m) =>
        m.full_name?.toLowerCase().includes(q) ||
        m.email.toLowerCase().includes(q) ||
        m.organization_role.toLowerCase().includes(q)
    )
  }, [members, search])

  const filteredInvitations = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return invitations
    return invitations.filter((i) => i.email?.toLowerCase().includes(q))
  }, [invitations, search])

  const organizationRoles = useMemo(
    () => roles.filter((role) => role.family === "organization").sort((a, b) => a.name.localeCompare(b.name)),
    [roles]
  )
  const projectRoles = useMemo(
    () => roles.filter((role) => role.family === "project").sort((a, b) => a.name.localeCompare(b.name)),
    [roles]
  )
  const projectById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects])
  const defaultProjectRoleId = useMemo(
    () => projectRoles.find((role) => role.is_preset && role.name === "Member")?.id || projectRoles[0]?.id || "",
    [projectRoles]
  )
  const filteredOrganizationRoles = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return organizationRoles
    return organizationRoles.filter((role) => role.name.toLowerCase().includes(q) || role.description?.toLowerCase().includes(q))
  }, [organizationRoles, search])
  const filteredProjectRoles = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return projectRoles
    return projectRoles.filter((role) => role.name.toLowerCase().includes(q) || role.description?.toLowerCase().includes(q))
  }, [projectRoles, search])
  const organizationRoleByUserId = useMemo(() => {
    const map = new Map<string, SettingsRoleAssignment>()
    assignments
      .filter((assignment) => assignment.assignment_kind === "organization" && assignment.role_family === "organization")
      .forEach((assignment) => {
        map.set(assignment.user_id, assignment)
      })
    return map
  }, [assignments])
  const projectAccessCountByUserId = useMemo(() => {
    const counts = new Map<string, number>()
    assignments
      .filter((assignment) => assignment.assignment_kind === "project" && assignment.role_family === "project")
      .forEach((assignment) => {
        counts.set(assignment.user_id, (counts.get(assignment.user_id) || 0) + 1)
      })
    return counts
  }, [assignments])
  const pendingInviteCountByRoleId = useMemo(() => {
    const counts = new Map<string, number>()
    invitations.forEach((invite) => {
      if (!invite.project_role_id) return
      counts.set(invite.project_role_id, (counts.get(invite.project_role_id) || 0) + 1)
    })
    return counts
  }, [invitations])
  const roleAssignmentCountByRoleId = useMemo(() => {
    const counts = new Map<string, number>()
    assignments.forEach((assignment) => {
      counts.set(assignment.role_id, (counts.get(assignment.role_id) || 0) + 1)
    })
    return counts
  }, [assignments])

  // ── Actions ──

  const resetRoleForm = () => {
    setRoleForm({
      id: "",
      family: "",
      name: "",
      description: "",
      permissions: [],
    })
  }

  const createInvitation = async () => {
    if (!inviteEmail.trim()) return
    setInviteSaving(true)
    setError(null)
    try {
      await settingsPeoplePermissionsService.createInvitation({
        email: inviteEmail.trim(),
        project_ids: inviteProjectId ? [inviteProjectId] : [],
        project_role_id: inviteProjectId ? (inviteProjectRoleId || defaultProjectRoleId || null) : null,
      })
      setInviteEmail("")
      setInviteProjectId("")
      setInviteProjectRoleId(defaultProjectRoleId)
      setInviteOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create invitation."))
    } finally {
      setInviteSaving(false)
    }
  }

  const createGroup = async () => {
    if (!groupForm.name.trim()) return
    setGroupSaving(true)
    setError(null)
    try {
      await settingsPeoplePermissionsService.createGroup({
        name: groupForm.name.trim(),
        type: groupForm.type as "org" | "dept" | "team",
        parent_id: groupForm.parent_id || null,
      })
      setGroupForm({ name: "", type: "team", parent_id: "" })
      setGroupOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create group."))
    } finally {
      setGroupSaving(false)
    }
  }

  const saveMemberRoles = async () => {
    if (!memberRoleTarget || !currentOrganization?.id || !memberRoleId) return
    const currentOrganizationAssignments = assignments.filter(
      (assignment) =>
        assignment.user_id === memberRoleTarget.user_id &&
        assignment.assignment_kind === "organization" &&
        assignment.role_family === "organization"
    )
    const currentRoleId = currentOrganizationAssignments[0]?.role_id || ""
    const currentProjectAssignments = assignments.filter(
      (assignment) =>
        assignment.user_id === memberRoleTarget.user_id &&
        assignment.assignment_kind === "project" &&
        assignment.role_family === "project"
    )
    const selectedOrganizationRole = organizationRoles.find((role) => role.id === memberRoleId)
    const isOrgOwner = selectedOrganizationRole?.name === "Owner"

    setMemberRoleSaving(true)
    setError(null)
    try {
      if (currentRoleId !== memberRoleId) {
        await settingsPeoplePermissionsService.createRoleAssignment({
          user_id: memberRoleTarget.user_id,
          role_id: memberRoleId,
          assignment_kind: "organization",
        })
      }
      const desiredProjectRows = isOrgOwner
        ? []
        : memberProjectAccessRows.filter((row) => row.projectId && row.roleId)
      const desiredByProjectId = new Map(desiredProjectRows.map((row) => [row.projectId, row]))

      for (const assignment of currentProjectAssignments) {
        if (!assignment.project_id || !desiredByProjectId.has(assignment.project_id)) {
          await settingsPeoplePermissionsService.deleteRoleAssignment(assignment.id)
        }
      }

      for (const row of desiredProjectRows) {
        const existing = currentProjectAssignments.find((assignment) => assignment.project_id === row.projectId)
        if (!existing || existing.role_id !== row.roleId) {
          await settingsPeoplePermissionsService.createRoleAssignment({
            user_id: memberRoleTarget.user_id,
            role_id: row.roleId,
            assignment_kind: "project",
            project_id: row.projectId,
          })
        }
      }
      setMemberRoleTarget(null)
      setMemberRoleId("")
      setMemberProjectAccessRows([])
      setMemberRoleOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to update member roles."))
    } finally {
      setMemberRoleSaving(false)
    }
  }

  const saveRole = async () => {
    if (!roleForm.family || !roleForm.name.trim()) return
    setRoleSaving(true)
    setError(null)
    try {
      if (roleForm.id) {
        await settingsPeoplePermissionsService.updateRole(roleForm.id, {
          family: roleForm.family,
          name: roleForm.name.trim(),
          description: roleForm.description.trim() || null,
          permissions: roleForm.permissions,
        })
      } else {
        await settingsPeoplePermissionsService.createRole({
          family: roleForm.family,
          name: roleForm.name.trim(),
          description: roleForm.description.trim() || null,
          permissions: roleForm.permissions,
        })
      }
      setRoleOpen(false)
      resetRoleForm()
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save role."))
    } finally {
      setRoleSaving(false)
    }
  }

  const openCreateRole = () => {
    resetRoleForm()
    setRoleOpen(true)
  }

  const openEditRole = (role: SettingsRole) => {
    setRoleForm({
      id: role.id,
      family: role.family,
      name: role.name,
      description: role.description || "",
      permissions: role.permissions,
    })
    setRoleOpen(true)
  }

  // Current tab action button
  const renderActionButton = () => {
    switch (activeTab) {
      case "members":
        return null
      case "invitations":
        return (
          <Button size="sm" className="h-8 text-xs shrink-0" onClick={() => setInviteOpen(true)}>
            <UserPlus className="h-3.5 w-3.5 mr-1.5" />
            Invite
          </Button>
        )
      case "groups":
        return (
          <Button size="sm" className="h-8 text-xs shrink-0" onClick={() => setGroupOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            New Group
          </Button>
        )
      case "roles":
        return (
          <Button size="sm" className="h-8 text-xs shrink-0" onClick={openCreateRole}>
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            Create Role
          </Button>
        )
      default:
        return null
    }
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-sm font-medium text-foreground">People & Permissions</h2>
        <p className="text-xs text-muted-foreground/70 mt-0.5">
          Members, invitations, groups, roles, and access assignments.
        </p>
      </div>

      <ErrorBanner message={error} />

      {loading ? (
        <p className="text-xs text-muted-foreground py-8 text-center">Loading…</p>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-0">
          {/* ── Toolbar row: search + tabs + action button ── */}
        <div className="flex flex-wrap pb-4 items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              wrapperClassName="w-56"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {renderActionButton()}
            <TabsList>
              <TabsTrigger value="members">Members</TabsTrigger>
              <TabsTrigger value="invitations">Invitations</TabsTrigger>
              <TabsTrigger value="groups">Groups</TabsTrigger>
              <TabsTrigger value="roles">Roles</TabsTrigger>
            </TabsList>
          </div>
        </div>

          {/* ── Members ── */}
          <TabsContent value="members">
            {filteredMembers.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm font-medium text-muted-foreground">No members found</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  {search ? "Try a different search term" : "No members in this organization yet"}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/30">
                {filteredMembers.map((member) => (
                  <div
                    key={member.membership_id}
                    className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">
                          {member.full_name || member.email}
                        </span>
                        <span className="flex shrink-0 items-center gap-1">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          <span className="text-xs text-muted-foreground/60">
                            {organizationRoleByUserId.get(member.user_id)?.role_name || member.organization_role}
                          </span>
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span className="text-xs text-muted-foreground/50">{member.email}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/40">{member.org_unit_name}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/40">
                          {projectAccessCountByUserId.get(member.user_id) || 0} project{(projectAccessCountByUserId.get(member.user_id) || 0) === 1 ? "" : "s"}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          setMemberRoleTarget(member)
                          setMemberRoleId(organizationRoleByUserId.get(member.user_id)?.role_id || "")
                          setMemberProjectAccessRows(
                            assignments
                              .filter(
                                (assignment) =>
                                  assignment.user_id === member.user_id &&
                                  assignment.assignment_kind === "project" &&
                                  assignment.role_family === "project"
                              )
                              .map((assignment) => ({
                                assignmentId: assignment.id,
                                projectId: assignment.project_id || "",
                                roleId: assignment.role_id,
                              }))
                          )
                          setMemberRoleOpen(true)
                        }}
                      >
                        Manage Access
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive h-7 text-xs"
                        onClick={() => void settingsPeoplePermissionsService.removeMember(member.membership_id).then(load)}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Invitations ── */}
          <TabsContent value="invitations">
            {filteredInvitations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm font-medium text-muted-foreground">No pending invitations</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Use the Invite button above to send a new invitation.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/30">
                {filteredInvitations.map((invite) => (
                  <div
                    key={invite.id}
                    className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium">{invite.email || "Unknown email"}</span>
                      <p className="text-xs text-muted-foreground/50 mt-0.5">
                        Expires {invite.expires_at || "unknown"}
                      </p>
                      {invite.project_ids[0] ? (
                        <p className="text-[11px] text-muted-foreground/45 mt-1">
                          {projectById.get(invite.project_ids[0])?.name || "Unknown project"} · {invite.project_role || "Member"}
                        </p>
                      ) : null}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive h-7 text-xs shrink-0"
                      onClick={() => void settingsPeoplePermissionsService.revokeInvitation(invite.id).then(load)}
                    >
                      Revoke
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Groups ── */}
          <TabsContent value="groups">
            {groups.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm font-medium text-muted-foreground">No groups yet</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Create your first group to organize members.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/30">
                {groups.map((group) => (
                  <div
                    key={group.id}
                    className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{group.name}</span>
                        {!group.parent_id && (
                          <Badge variant="secondary" className="text-[10px] h-4">Root</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground/50 mt-0.5">
                        {group.type}
                      </p>
                    </div>
                    {group.parent_id ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive h-7 text-xs shrink-0"
                        onClick={() => void settingsPeoplePermissionsService.deleteGroup(group.id).then(load)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Roles + Assignments ── */}
          <TabsContent value="roles">
            {roles.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm font-medium text-muted-foreground">No roles configured</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Use Create Role to add the first custom role for this organization.
                </p>
              </div>
            ) : (
              <div className="space-y-8">
                <div>
                  <div className="mb-3">
                    <h3 className="text-sm font-semibold text-foreground">Organization Roles</h3>
                    <p className="text-xs text-muted-foreground/60 mt-0.5">Govern organization settings, people, and projects.</p>
                  </div>
                  <div className="divide-y divide-border/30">
                    {filteredOrganizationRoles.map((role) => (
                      <div key={role.id} className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{role.name}</span>
                            {role.is_preset ? <Badge variant="secondary" className="text-[10px] h-4">Preset</Badge> : null}
                          </div>
                          <p className="text-xs text-muted-foreground/50 mt-0.5">{role.description || role.permissions.join(", ") || "No permissions"}</p>
                          <p className="text-[11px] text-muted-foreground/45 mt-1">
                            {roleAssignmentCountByRoleId.get(role.id) || 0} assignment{(roleAssignmentCountByRoleId.get(role.id) || 0) === 1 ? "" : "s"}
                            {pendingInviteCountByRoleId.get(role.id) ? ` · ${pendingInviteCountByRoleId.get(role.id)} pending invite${pendingInviteCountByRoleId.get(role.id) === 1 ? "" : "s"}` : ""}
                          </p>
                        </div>
                        {!role.is_preset ? (
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => openEditRole(role)}>
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive h-7 text-xs"
                              disabled={Boolean(roleAssignmentCountByRoleId.get(role.id)) || Boolean(pendingInviteCountByRoleId.get(role.id))}
                              onClick={() => void settingsPeoplePermissionsService.deleteRole(role.id).then(load)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-3">
                    <h3 className="text-sm font-semibold text-foreground">Project Roles</h3>
                    <p className="text-xs text-muted-foreground/60 mt-0.5">Govern build, preview, and publish access inside projects.</p>
                  </div>
                  <div className="divide-y divide-border/30">
                    {filteredProjectRoles.map((role) => (
                      <div key={role.id} className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{role.name}</span>
                            {role.is_preset ? <Badge variant="secondary" className="text-[10px] h-4">Preset</Badge> : null}
                          </div>
                          <p className="text-xs text-muted-foreground/50 mt-0.5">{role.description || role.permissions.join(", ") || "No permissions"}</p>
                          <p className="text-[11px] text-muted-foreground/45 mt-1">
                            {roleAssignmentCountByRoleId.get(role.id) || 0} assignment{(roleAssignmentCountByRoleId.get(role.id) || 0) === 1 ? "" : "s"}
                            {pendingInviteCountByRoleId.get(role.id) ? ` · ${pendingInviteCountByRoleId.get(role.id)} pending invite${pendingInviteCountByRoleId.get(role.id) === 1 ? "" : "s"}` : ""}
                          </p>
                        </div>
                        {!role.is_preset ? (
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => openEditRole(role)}>
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive h-7 text-xs"
                              disabled={Boolean(roleAssignmentCountByRoleId.get(role.id)) || Boolean(pendingInviteCountByRoleId.get(role.id))}
                              onClick={() => void settingsPeoplePermissionsService.deleteRole(role.id).then(load)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── Assignments sub-section ── */}
            {assignments.length > 0 && (
              <div className="mt-8">
                <div className="mb-3">
                  <h3 className="text-sm font-semibold text-foreground">Assignments</h3>
                  <p className="text-xs text-muted-foreground/60 mt-0.5">Active role assignments in the organization.</p>
                </div>
                <div className="divide-y divide-border/30">
                  {assignments.map((assignment) => (
                    <div
                      key={assignment.id}
                      className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
                    >
                      <div className="flex items-center gap-2 text-sm min-w-0">
                        <span className="font-medium truncate">{assignment.user_email}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/60">{assignment.role_family}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/60">{assignment.role_name}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/40">{assignment.assignment_kind}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive h-7 text-xs shrink-0"
                        onClick={() => void settingsPeoplePermissionsService.deleteRoleAssignment(assignment.id).then(load)}
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}

      {/* ═══════════ Modals ═══════════ */}

      {/* ── Invite Modal ── */}
      <Dialog open={inviteOpen} onOpenChange={(open) => { setInviteOpen(open); if (!open) { setInviteEmail(""); setInviteProjectId(""); setInviteProjectRoleId(defaultProjectRoleId) } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">Invite Member</DialogTitle>
            <DialogDescription className="text-xs">Send an invitation to join the organization.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Email</Label>
              <Input
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="name@example.com"
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Initial Project (optional)</Label>
              <Select value={inviteProjectId || "__none__"} onValueChange={(value) => setInviteProjectId(value === "__none__" ? "" : value)}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="No initial project" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">No initial project</SelectItem>
                  {projects.map((project) => (
                    <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground/70">
                Organization role defaults to Reader. If a project is selected, project access defaults to Member.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Project Role</Label>
              <Select
                value={inviteProjectRoleId || defaultProjectRoleId || undefined}
                onValueChange={setInviteProjectRoleId}
                disabled={!inviteProjectId}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Member" />
                </SelectTrigger>
                <SelectContent>
                  {projectRoles.map((role) => (
                    <SelectItem key={role.id} value={role.id}>{role.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setInviteOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={createInvitation} disabled={inviteSaving || !inviteEmail.trim()}>
                {inviteSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Send Invitation
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Group Modal ── */}
      <Dialog open={groupOpen} onOpenChange={(open) => { setGroupOpen(open); if (!open) setGroupForm({ name: "", type: "team", parent_id: "" }) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">New Group</DialogTitle>
            <DialogDescription className="text-xs">Create a new organizational group.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Name</Label>
              <Input value={groupForm.name} onChange={(e) => setGroupForm((c) => ({ ...c, name: e.target.value }))} placeholder="Engineering" className="h-9" />
            </div>
                        <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={groupForm.type} onValueChange={(value) => setGroupForm((c) => ({ ...c, type: value }))}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="dept">Department</SelectItem>
                  <SelectItem value="team">Team</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setGroupOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={createGroup} disabled={groupSaving || !groupForm.name.trim()}>
                {groupSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Create Group
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <MemberRoleAssignmentsDialog
        open={memberRoleOpen}
        member={memberRoleTarget}
        organizationRoles={organizationRoles}
        projectRoles={projectRoles}
        projects={projects}
        selectedOrganizationRoleId={memberRoleId}
        projectAccessRows={memberProjectAccessRows}
        orgOwnerImplicit={organizationRoles.find((role) => role.id === memberRoleId)?.name === "Owner"}
        saving={memberRoleSaving}
        onSelectedOrganizationRoleIdChange={setMemberRoleId}
        onProjectAccessRowsChange={setMemberProjectAccessRows}
        onOpenChange={(open) => {
          setMemberRoleOpen(open)
          if (!open) {
            setMemberRoleTarget(null)
            setMemberRoleId("")
            setMemberProjectAccessRows([])
          }
        }}
        onSave={saveMemberRoles}
      />

      <RolePermissionDialog
        open={roleOpen}
        form={roleForm}
        saving={roleSaving}
        assignmentCount={roleForm.id ? (roleAssignmentCountByRoleId.get(roleForm.id) || 0) : 0}
        onFormChange={setRoleForm}
        onOpenChange={(open) => {
          setRoleOpen(open)
          if (!open) resetRoleForm()
        }}
        onSave={saveRole}
      />
    </div>
  )
}
