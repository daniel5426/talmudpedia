"use client"

import { useMemo } from "react"
import { AlertTriangle } from "lucide-react"

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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { SettingsRole } from "@/services"

export type RoleFormState = {
  id: string
  family: SettingsRole["family"] | ""
  name: string
  description: string
  permissions: string[]
}

type AccessValue = "none" | "read" | "write"

type PermissionResource = {
  id: string
  label: string
  description: string
  readScopes: string[]
  writeScopes?: string[]
  dangerous?: boolean
}

interface RolePermissionDialogProps {
  open: boolean
  form: RoleFormState
  saving: boolean
  assignmentCount: number
  onFormChange: (next: RoleFormState) => void
  onOpenChange: (open: boolean) => void
  onSave: () => void
}

const ORGANIZATION_RESOURCES: PermissionResource[] = [
  {
    id: "organization",
    label: "Organization Settings",
    description: "Read or manage organization settings and defaults.",
    readScopes: ["organizations.read"],
    writeScopes: ["organizations.read", "organizations.write"],
  },
  {
    id: "members",
    label: "Members",
    description: "View and manage organization members.",
    readScopes: ["organization_members.read"],
    writeScopes: ["organization_members.read", "organization_members.write", "organization_members.delete"],
    dangerous: true,
  },
  {
    id: "invites",
    label: "Invitations",
    description: "Send, review, and revoke invitations.",
    readScopes: ["organization_invites.read"],
    writeScopes: ["organization_invites.read", "organization_invites.write", "organization_invites.delete"],
  },
  {
    id: "groups",
    label: "Groups",
    description: "Manage organization structure and groups.",
    readScopes: ["organization_units.read"],
    writeScopes: ["organization_units.read", "organization_units.write", "organization_units.delete"],
  },
  {
    id: "projects",
    label: "Projects",
    description: "View and manage projects in the organization.",
    readScopes: ["projects.read"],
    writeScopes: ["projects.read", "projects.write", "projects.archive"],
  },
  {
    id: "roles",
    label: "Roles & Assignments",
    description: "Manage custom roles and role assignments.",
    readScopes: ["roles.read"],
    writeScopes: ["roles.read", "roles.write", "roles.assign"],
    dangerous: true,
  },
  {
    id: "audit",
    label: "Audit & Usage",
    description: "Read audit logs and usage dashboards.",
    readScopes: ["audit.read", "stats.read"],
  },
  {
    id: "users",
    label: "Users",
    description: "View and manage platform user records.",
    readScopes: ["users.read"],
    writeScopes: ["users.read", "users.write"],
  },
]

const PROJECT_RESOURCES: PermissionResource[] = [
  {
    id: "apps",
    label: "Apps",
    description: "Read and build apps inside the project.",
    readScopes: ["apps.read"],
    writeScopes: ["apps.read", "apps.write"],
  },
  {
    id: "agents",
    label: "Agents",
    description: "Build, execute, test, and expose agents.",
    readScopes: ["agents.read"],
    writeScopes: ["agents.read", "agents.write", "agents.execute", "agents.run_tests", "agents.embed"],
  },
  {
    id: "threads",
    label: "Threads",
    description: "Inspect and manage project threads.",
    readScopes: ["threads.read"],
    writeScopes: ["threads.read", "threads.write"],
  },
  {
    id: "pipelines",
    label: "Pipelines",
    description: "Read and edit RAG pipelines.",
    readScopes: ["pipelines.catalog.read", "pipelines.read"],
    writeScopes: ["pipelines.catalog.read", "pipelines.read", "pipelines.write", "pipelines.delete"],
  },
  {
    id: "tools",
    label: "Tools",
    description: "View and manage project tools.",
    readScopes: ["tools.read"],
    writeScopes: ["tools.read", "tools.write", "tools.delete"],
  },
  {
    id: "artifacts",
    label: "Artifacts",
    description: "View and manage artifacts.",
    readScopes: ["artifacts.read"],
    writeScopes: ["artifacts.read", "artifacts.write", "artifacts.delete"],
  },
  {
    id: "files",
    label: "Files",
    description: "Browse and update project files.",
    readScopes: ["files.read"],
    writeScopes: ["files.read", "files.write"],
  },
  {
    id: "knowledge_stores",
    label: "Knowledge Stores",
    description: "Manage knowledge stores and retrieval data.",
    readScopes: ["knowledge_stores.read"],
    writeScopes: ["knowledge_stores.read", "knowledge_stores.write"],
  },
  {
    id: "models",
    label: "Models",
    description: "Read and manage project model usage.",
    readScopes: ["models.read"],
    writeScopes: ["models.read", "models.write"],
  },
  {
    id: "prompts",
    label: "Prompts",
    description: "Read and edit prompts.",
    readScopes: ["prompts.read"],
    writeScopes: ["prompts.read", "prompts.write"],
  },
  {
    id: "credentials",
    label: "Credentials",
    description: "Read and manage provider credentials.",
    readScopes: ["credentials.read"],
    writeScopes: ["credentials.read", "credentials.write"],
    dangerous: true,
  },
  {
    id: "api_keys",
    label: "Project API Keys",
    description: "Read and manage project API keys.",
    readScopes: ["api_keys.read"],
    writeScopes: ["api_keys.read", "api_keys.write"],
    dangerous: true,
  },
]

function deriveAccessValue(resource: PermissionResource, permissions: string[]): AccessValue {
  const set = new Set(permissions)
  if (resource.writeScopes && resource.writeScopes.every((scope) => set.has(scope))) {
    return "write"
  }
  if (resource.readScopes.every((scope) => set.has(scope))) {
    return "read"
  }
  return "none"
}

function updatePermissionsForResource(resource: PermissionResource, nextValue: AccessValue, permissions: string[]): string[] {
  const next = new Set(permissions)
  for (const scope of [...resource.readScopes, ...(resource.writeScopes || [])]) {
    next.delete(scope)
  }
  if (nextValue === "read") {
    for (const scope of resource.readScopes) next.add(scope)
  }
  if (nextValue === "write") {
    for (const scope of resource.writeScopes || resource.readScopes) next.add(scope)
  }
  return Array.from(next).sort()
}

export function RolePermissionDialog({
  open,
  form,
  saving,
  assignmentCount,
  onFormChange,
  onOpenChange,
  onSave,
}: RolePermissionDialogProps) {
  const resources = useMemo(() => {
    if (form.family === "organization") return ORGANIZATION_RESOURCES
    if (form.family === "project") return PROJECT_RESOURCES
    return []
  }, [form.family])

  const isEditing = Boolean(form.id)
  const canSave = Boolean(form.family && form.name.trim())

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="text-base">{isEditing ? "Edit custom role" : "Create custom role"}</DialogTitle>
          <DialogDescription className="text-xs">
            {isEditing
              ? "Adjust one role family only. Preset roles remain immutable."
              : "Create a family-specific custom role without mixing organization and project permissions."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Role family</Label>
              <Select
                value={form.family || undefined}
                onValueChange={(value) => onFormChange({ ...form, family: value as SettingsRole["family"], permissions: [] })}
                disabled={isEditing}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Choose a role family" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="organization">Organization</SelectItem>
                  <SelectItem value="project">Project</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Role name</Label>
              <Input
                value={form.name}
                onChange={(event) => onFormChange({ ...form, name: event.target.value })}
                placeholder={form.family === "project" ? "Workflow Builder" : "Support Admin"}
                className="h-9"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Description</Label>
            <Textarea
              value={form.description}
              onChange={(event) => onFormChange({ ...form, description: event.target.value })}
              placeholder="Describe what this role is for."
              className="min-h-[88px] text-sm"
            />
          </div>

          {isEditing && assignmentCount > 0 ? (
            <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{assignmentCount} active assignment{assignmentCount === 1 ? "" : "s"}. Changes apply immediately to those members.</span>
            </div>
          ) : null}

          {form.family ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-foreground">
                    {form.family === "organization" ? "Organization permissions" : "Project permissions"}
                  </h3>
                  <p className="text-xs text-muted-foreground/70 mt-0.5">
                    {form.family === "organization"
                      ? "Governance permissions for settings, people, roles, and org-wide visibility."
                      : "Build, run, and manage work inside a project. Dangerous capabilities stay explicit."}
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {form.permissions.length} scope{form.permissions.length === 1 ? "" : "s"}
                </Badge>
              </div>

              <div className="space-y-2 max-h-[44vh] overflow-y-auto pr-1">
                {resources.map((resource) => {
                  const access = deriveAccessValue(resource, form.permissions)
                  return (
                    <div key={resource.id} className="rounded-xl border border-border/50 px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-foreground">{resource.label}</span>
                            {resource.dangerous ? <Badge variant="secondary" className="h-5 text-[10px]">Sensitive</Badge> : null}
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground/75">{resource.description}</p>
                        </div>
                        <Select
                          value={access}
                          onValueChange={(value) =>
                            onFormChange({
                              ...form,
                              permissions: updatePermissionsForResource(resource, value as AccessValue, form.permissions),
                            })
                          }
                        >
                          <SelectTrigger className={cn("h-8 w-[112px] text-xs", access === "write" ? "border-primary/50" : undefined)}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">None</SelectItem>
                            <SelectItem value="read">Read</SelectItem>
                            {resource.writeScopes ? <SelectItem value="write">Write</SelectItem> : null}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving || !canSave}>
            {saving ? "Saving..." : isEditing ? "Save role" : "Create role"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
