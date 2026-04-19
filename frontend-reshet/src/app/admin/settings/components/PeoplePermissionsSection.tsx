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
import { RolePermissionDialog } from "@/app/admin/settings/components/RolePermissionDialog"

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
  const [roleOpen, setRoleOpen] = useState(false)
  const [memberRoleOpen, setMemberRoleOpen] = useState(false)

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteProjectId, setInviteProjectId] = useState<string>("")
  const [inviteSaving, setInviteSaving] = useState(false)

  // Group form
  const [groupForm, setGroupForm] = useState({ name: "", slug: "", type: "team", parent_id: "" })
  const [groupSaving, setGroupSaving] = useState(false)

  // Role form
  const [roleForm, setRoleForm] = useState({ id: "", name: "", description: "", permissions: [] as string[] })
  const [roleSaving, setRoleSaving] = useState(false)

  // Member role assignment
  const [memberRoleTarget, setMemberRoleTarget] = useState<SettingsMember | null>(null)
  const [memberRoleIds, setMemberRoleIds] = useState<string[]>([])
  const [memberRoleSaving, setMemberRoleSaving] = useState(false)

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

  const rootGroupId = useMemo(() => groups.find((group) => group.parent_id === null)?.id || "", [groups])

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

  // ── Actions ──

  const createInvitation = async () => {
    if (!inviteEmail.trim()) return
    setInviteSaving(true)
    setError(null)
    try {
      await settingsPeoplePermissionsService.createInvitation({
        email: inviteEmail.trim(),
        project_ids: inviteProjectId ? [inviteProjectId] : [],
      })
      setInviteEmail("")
      setInviteProjectId("")
      setInviteOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create invitation."))
    } finally {
      setInviteSaving(false)
    }
  }

  const createGroup = async () => {
    if (!groupForm.name.trim() || !groupForm.slug.trim()) return
    setGroupSaving(true)
    setError(null)
    try {
      await settingsPeoplePermissionsService.createGroup({
        name: groupForm.name.trim(),
        slug: groupForm.slug.trim(),
        type: groupForm.type as "org" | "dept" | "team",
        parent_id: groupForm.parent_id || null,
      })
      setGroupForm({ name: "", slug: "", type: "team", parent_id: "" })
      setGroupOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create group."))
    } finally {
      setGroupSaving(false)
    }
  }

  const saveRole = async () => {
    const payload = {
      name: roleForm.name.trim(),
      description: roleForm.description.trim() || null,
      permissions: roleForm.permissions
        .map((value) => value.trim())
        .filter(Boolean),
    }
    if (!payload.name) return
    setRoleSaving(true)
    setError(null)
    try {
      if (roleForm.id) {
        await settingsPeoplePermissionsService.updateRole(roleForm.id, payload)
      } else {
        await settingsPeoplePermissionsService.createRole(payload)
      }
      setRoleForm({ id: "", name: "", description: "", permissions: [] })
      setRoleOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save role."))
    } finally {
      setRoleSaving(false)
    }
  }

  const saveMemberRoles = async () => {
    if (!memberRoleTarget) return
    const scopeId = rootGroupId || memberRoleTarget.org_unit_id
    if (!scopeId) return
    const currentAssignments = assignments.filter(
      (assignment) => assignment.user_id === memberRoleTarget.user_id && assignment.scope_type === "organization"
    )
    const currentRoleIds = new Set(currentAssignments.map((assignment) => assignment.role_id))
    const nextRoleIds = new Set(memberRoleIds)
    const assignmentIdsToDelete = currentAssignments
      .filter((assignment) => !nextRoleIds.has(assignment.role_id))
      .map((assignment) => assignment.id)
    const roleIdsToCreate = memberRoleIds.filter((roleId) => !currentRoleIds.has(roleId))

    setMemberRoleSaving(true)
    setError(null)
    try {
      await Promise.all([
        ...roleIdsToCreate.map((roleId) =>
          settingsPeoplePermissionsService.createRoleAssignment({
            user_id: memberRoleTarget.user_id,
            role_id: roleId,
            scope_type: "organization",
            scope_id: scopeId,
          })
        ),
        ...assignmentIdsToDelete.map((assignmentId) =>
          settingsPeoplePermissionsService.deleteRoleAssignment(assignmentId)
        ),
      ])
      setMemberRoleTarget(null)
      setMemberRoleIds([])
      setMemberRoleOpen(false)
      await load()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to update member roles."))
    } finally {
      setMemberRoleSaving(false)
    }
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
          <Button
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              setRoleForm({ id: "", name: "", description: "", permissions: [] })
              setRoleOpen(true)
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1.5" />
            New Role
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
        <div className="flex flex-wrap items-center justify-between gap-3">
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
                          <span className="text-xs text-muted-foreground/60">{member.organization_role}</span>
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span className="text-xs text-muted-foreground/50">{member.email}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/40">{member.org_unit_name}</span>
                      </div>
                      {assignments.some((assignment) => assignment.user_id === member.user_id && assignment.scope_type === "organization") ? (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {assignments
                            .filter((assignment) => assignment.user_id === member.user_id && assignment.scope_type === "organization")
                            .map((assignment) => (
                              <Badge key={assignment.id} variant="secondary" className="h-5 px-1.5 text-[10px]">
                                {assignment.role_name}
                              </Badge>
                            ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          setMemberRoleTarget(member)
                          setMemberRoleIds(
                            assignments
                              .filter((assignment) => assignment.user_id === member.user_id && assignment.scope_type === "organization")
                              .map((assignment) => assignment.role_id)
                          )
                          setMemberRoleOpen(true)
                        }}
                      >
                        Edit Roles
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
                        {group.slug} · {group.type}
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
                  Create a custom role to define fine-grained permissions.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/30">
                {roles.map((role) => (
                  <div
                    key={role.id}
                    className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{role.name}</span>
                        {role.is_system && (
                          <Badge variant="secondary" className="text-[10px] h-4">System</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground/50 mt-0.5">
                        {role.permissions.join(", ") || "No permissions"}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          setRoleForm({
                            id: role.id,
                            name: role.name,
                            description: role.description || "",
                            permissions: role.permissions,
                          })
                          setRoleOpen(true)
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive h-7 text-xs"
                        onClick={() => void settingsPeoplePermissionsService.deleteRole(role.id).then(load)}
                        disabled={role.is_system}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
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
                        <span className="text-xs text-muted-foreground/60">{assignment.role_name}</span>
                        <span className="text-muted-foreground/30">·</span>
                        <span className="text-xs text-muted-foreground/40">{assignment.scope_type}</span>
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
      <Dialog open={inviteOpen} onOpenChange={(open) => { setInviteOpen(open); if (!open) { setInviteEmail(""); setInviteProjectId("") } }}>
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
      <Dialog open={groupOpen} onOpenChange={(open) => { setGroupOpen(open); if (!open) setGroupForm({ name: "", slug: "", type: "team", parent_id: "" }) }}>
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
              <Label className="text-xs">Slug</Label>
              <Input value={groupForm.slug} onChange={(e) => setGroupForm((c) => ({ ...c, slug: e.target.value }))} placeholder="engineering" className="h-9 font-mono text-xs" />
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
              <Button size="sm" onClick={createGroup} disabled={groupSaving || !groupForm.name.trim() || !groupForm.slug.trim()}>
                {groupSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Create Group
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Role Modal ── */}
      <RolePermissionDialog
        open={roleOpen}
        form={roleForm}
        saving={roleSaving}
        assignmentCount={roleForm.id ? assignments.filter((assignment) => assignment.role_id === roleForm.id).length : 0}
        onFormChange={setRoleForm}
        onOpenChange={setRoleOpen}
        onSave={saveRole}
      />

      <MemberRoleAssignmentsDialog
        open={memberRoleOpen}
        member={memberRoleTarget}
        roles={roles}
        selectedRoleIds={memberRoleIds}
        saving={memberRoleSaving}
        onSelectedRoleIdsChange={setMemberRoleIds}
        onOpenChange={(open) => {
          setMemberRoleOpen(open)
          if (!open) {
            setMemberRoleTarget(null)
            setMemberRoleIds([])
          }
        }}
        onSave={saveMemberRoles}
      />
    </div>
  )
}
