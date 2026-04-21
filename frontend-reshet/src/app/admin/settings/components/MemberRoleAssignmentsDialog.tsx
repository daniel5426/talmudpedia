"use client"

import { Plus, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SettingsMember, SettingsProject, SettingsRole } from "@/services"

type ProjectAccessRow = {
  assignmentId?: string
  projectId: string
  roleId: string
}

interface MemberRoleAssignmentsDialogProps {
  open: boolean
  member: SettingsMember | null
  organizationRoles: SettingsRole[]
  projectRoles: SettingsRole[]
  projects: SettingsProject[]
  selectedOrganizationRoleId: string
  projectAccessRows: ProjectAccessRow[]
  orgOwnerImplicit: boolean
  saving: boolean
  onSelectedOrganizationRoleIdChange: (next: string) => void
  onProjectAccessRowsChange: (next: ProjectAccessRow[]) => void
  onOpenChange: (open: boolean) => void
  onSave: () => void
}

export function MemberRoleAssignmentsDialog({
  open,
  member,
  organizationRoles,
  projectRoles,
  projects,
  selectedOrganizationRoleId,
  projectAccessRows,
  orgOwnerImplicit,
  saving,
  onSelectedOrganizationRoleIdChange,
  onProjectAccessRowsChange,
  onOpenChange,
  onSave,
}: MemberRoleAssignmentsDialogProps) {
  const selectedProjectIds = new Set(projectAccessRows.map((row) => row.projectId).filter(Boolean))

  const updateProjectAccessRow = (index: number, patch: Partial<ProjectAccessRow>) => {
    const next = [...projectAccessRows]
    next[index] = { ...next[index], ...patch }
    onProjectAccessRowsChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-base">Manage access</DialogTitle>
          <DialogDescription className="text-xs">
            Update the organization role and explicit project access for {member?.full_name || member?.email || "this member"}.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {member ? (
            <div className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3">
              <p className="text-sm font-medium text-foreground">{member.full_name || member.email}</p>
              <p className="text-xs text-muted-foreground/70">{member.email}</p>
            </div>
          ) : null}

          <div className="space-y-3">
            <div>
              <h3 className="text-sm font-medium text-foreground">Organization role</h3>
              <p className="mt-0.5 text-xs text-muted-foreground/70">Exactly one organization-family role applies at the organization level.</p>
            </div>
            <div className="grid gap-2">
              {organizationRoles.map((role) => (
                <button
                  key={role.id}
                  type="button"
                  className={`rounded-xl border px-4 py-3 text-left transition-colors ${selectedOrganizationRoleId === role.id ? "border-primary bg-primary/5" : "border-border/50 hover:bg-muted/20"}`}
                  onClick={() => onSelectedOrganizationRoleIdChange(role.id)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{role.name}</span>
                    {role.is_preset ? <Badge variant="secondary" className="h-5 text-[10px]">Preset</Badge> : null}
                  </div>
                  {role.description ? <p className="mt-0.5 text-xs text-muted-foreground/75">{role.description}</p> : null}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-medium text-foreground">Project access</h3>
                <p className="mt-0.5 text-xs text-muted-foreground/70">Explicit project memberships and project-family roles.</p>
              </div>
              {!orgOwnerImplicit ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => onProjectAccessRowsChange([...projectAccessRows, { projectId: "", roleId: projectRoles[0]?.id || "" }])}
                  disabled={projectAccessRows.length >= projects.length || projectRoles.length === 0}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Add Project
                </Button>
              ) : null}
            </div>

            {orgOwnerImplicit ? (
              <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
                <p className="text-sm font-medium text-foreground">Has implicit access to all projects via Organization Owner.</p>
                <p className="mt-0.5 text-xs text-muted-foreground/70">Explicit project rows are not required while the organization role is Owner.</p>
              </div>
            ) : projectAccessRows.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border/60 px-4 py-5 text-sm text-muted-foreground/70">
                No explicit project access yet.
              </div>
            ) : (
              <div className="space-y-2">
                {projectAccessRows.map((row, index) => {
                  const availableProjects = projects.filter((project) => project.id === row.projectId || !selectedProjectIds.has(project.id))
                  return (
                    <div key={row.assignmentId || `row-${index}`} className="rounded-xl border border-border/50 px-4 py-3">
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
                        <div className="space-y-1.5">
                          <Label className="text-xs">Project</Label>
                          <Select
                            value={row.projectId || undefined}
                            onValueChange={(value) => updateProjectAccessRow(index, { projectId: value })}
                          >
                            <SelectTrigger className="h-9">
                              <SelectValue placeholder="Select project" />
                            </SelectTrigger>
                            <SelectContent>
                              {availableProjects.map((project) => (
                                <SelectItem key={project.id} value={project.id}>{project.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs">Project role</Label>
                          <Select
                            value={row.roleId || undefined}
                            onValueChange={(value) => updateProjectAccessRow(index, { roleId: value })}
                          >
                            <SelectTrigger className="h-9">
                              <SelectValue placeholder="Select project role" />
                            </SelectTrigger>
                            <SelectContent>
                              {projectRoles.map((role) => (
                                <SelectItem key={role.id} value={role.id}>{role.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-9 text-destructive"
                          onClick={() => onProjectAccessRowsChange(projectAccessRows.filter((_, currentIndex) => currentIndex !== index))}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving || !member || !selectedOrganizationRoleId}>
            {saving ? "Saving..." : "Save access"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
