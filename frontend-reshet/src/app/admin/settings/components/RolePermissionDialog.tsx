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
type RoleFormState = {
  id: string
  name: string
  description: string
  permissions: string[]
}

type AccessValue = "none" | "read" | "write"

type AccessOption = {
  value: Exclude<AccessValue, "none">
  label: string
  scopes: string[]
}

type PermissionResource = {
  id: string
  label: string
  description: string
  options: AccessOption[]
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

const EMPTY_ROLE: RoleFormState = { id: "", name: "", description: "", permissions: [] }

const PERMISSION_RESOURCES: PermissionResource[] = [
  {
    id: "models",
    label: "Models",
    description: "View and manage model inventory and providers.",
    options: [
      { value: "read", label: "Read", scopes: ["models.read"] },
      { value: "write", label: "Write", scopes: ["models.read", "models.write"] },
    ],
  },
  {
    id: "agents",
    label: "Agents",
    description: "Build, publish, and run agents.",
    options: [
      { value: "read", label: "Read", scopes: ["agents.read"] },
      {
        value: "write",
        label: "Write",
        scopes: [
          "agents.read",
          "agents.write",
          "agents.execute",
          "agents.run_tests",
          "agents.embed",
        ],
      },
    ],
  },
  {
    id: "threads",
    label: "Threads",
    description: "Inspect and manage conversation threads.",
    options: [
      { value: "read", label: "Read", scopes: ["threads.read"] },
      { value: "write", label: "Write", scopes: ["threads.read", "threads.write"] },
    ],
  },
  {
    id: "pipelines",
    label: "Pipelines",
    description: "Access the pipeline catalog and edit pipelines.",
    options: [
      { value: "read", label: "Read", scopes: ["pipelines.catalog.read", "pipelines.read"] },
      { value: "write", label: "Write", scopes: ["pipelines.catalog.read", "pipelines.read", "pipelines.write", "pipelines.delete"] },
    ],
  },
  {
    id: "tools",
    label: "Tools",
    description: "View and manage shared tools.",
    options: [
      { value: "read", label: "Read", scopes: ["tools.read"] },
      { value: "write", label: "Write", scopes: ["tools.read", "tools.write"] },
    ],
  },
  {
    id: "artifacts",
    label: "Artifacts",
    description: "Inspect and manage platform artifacts.",
    options: [
      { value: "read", label: "Read", scopes: ["artifacts.read"] },
      { value: "write", label: "Write", scopes: ["artifacts.read", "artifacts.write"] },
    ],
  },
  {
    id: "files",
    label: "Files",
    description: "Browse and update workspace files.",
    options: [
      { value: "read", label: "Read", scopes: ["files.read"] },
      { value: "write", label: "Write", scopes: ["files.read", "files.write"] },
    ],
  },
  {
    id: "knowledge_stores",
    label: "Knowledge Stores",
    description: "Manage vector and retrieval knowledge sources.",
    options: [
      { value: "read", label: "Read", scopes: ["knowledge_stores.read"] },
      { value: "write", label: "Write", scopes: ["knowledge_stores.read", "knowledge_stores.write"] },
    ],
  },
  {
    id: "prompts",
    label: "Prompts",
    description: "View and edit shared prompts.",
    options: [
      { value: "read", label: "Read", scopes: ["prompts.read"] },
      { value: "write", label: "Write", scopes: ["prompts.read", "prompts.write"] },
    ],
  },
  {
    id: "apps",
    label: "Apps",
    description: "Access and manage published apps.",
    options: [
      { value: "read", label: "Read", scopes: ["apps.read"] },
      { value: "write", label: "Write", scopes: ["apps.read", "apps.write"] },
    ],
  },
  {
    id: "api_keys",
    label: "Project API Keys",
    description: "View and manage API keys for project usage.",
    options: [
      { value: "read", label: "Read", scopes: ["api_keys.read"] },
      { value: "write", label: "Write", scopes: ["api_keys.read", "api_keys.write"] },
    ],
  },
  {
    id: "credentials",
    label: "Credentials",
    description: "View and manage external provider credentials.",
    options: [
      { value: "read", label: "Read", scopes: ["credentials.read"] },
      { value: "write", label: "Write", scopes: ["credentials.read", "credentials.write"] },
    ],
  },
  {
    id: "organization",
    label: "Organization",
    description: "Read or update organization settings.",
    options: [
      { value: "read", label: "Read", scopes: ["organizations.read"] },
      { value: "write", label: "Write", scopes: ["organizations.read", "organizations.write"] },
    ],
  },
  {
    id: "members",
    label: "Members",
    description: "View, invite, and manage organization members.",
    options: [
      { value: "read", label: "Read", scopes: ["organization_members.read"] },
      {
        value: "write",
        label: "Write",
        scopes: ["organization_members.read", "organization_members.write", "organization_members.delete"],
      },
    ],
  },
  {
    id: "invites",
    label: "Invitations",
    description: "Review and manage pending invitations.",
    options: [
      { value: "read", label: "Read", scopes: ["organization_invites.read"] },
      {
        value: "write",
        label: "Write",
        scopes: ["organization_invites.read", "organization_invites.write", "organization_invites.delete"],
      },
    ],
  },
  {
    id: "groups",
    label: "Groups",
    description: "Manage organizational units and hierarchy.",
    options: [
      { value: "read", label: "Read", scopes: ["organization_units.read"] },
      {
        value: "write",
        label: "Write",
        scopes: ["organization_units.read", "organization_units.write", "organization_units.delete"],
      },
    ],
  },
  {
    id: "projects",
    label: "Projects",
    description: "Read project information or manage project settings.",
    options: [
      { value: "read", label: "Read", scopes: ["projects.read"] },
      { value: "write", label: "Write", scopes: ["projects.read", "projects.write", "projects.archive"] },
    ],
  },
  {
    id: "roles",
    label: "Roles & Assignments",
    description: "Manage custom roles and role assignment workflows.",
    options: [
      { value: "read", label: "Read", scopes: ["roles.read"] },
      { value: "write", label: "Write", scopes: ["roles.read", "roles.write", "roles.assign"] },
    ],
  },
  {
    id: "audit_usage",
    label: "Audit & Usage",
    description: "Read audit logs and usage dashboards.",
    options: [
      { value: "read", label: "Read", scopes: ["audit.read", "stats.read"] },
    ],
  },
  {
    id: "users",
    label: "Users",
    description: "View and manage platform user records.",
    options: [
      { value: "read", label: "Read", scopes: ["users.read"] },
      { value: "write", label: "Write", scopes: ["users.read", "users.write"] },
    ],
  },
]

const KNOWN_SCOPES = new Set(
  PERMISSION_RESOURCES.flatMap((resource) => resource.options.flatMap((option) => option.scopes))
)

function getResourceScopes(resource: PermissionResource) {
  return new Set(resource.options.flatMap((option) => option.scopes))
}

function resolveResourceAccess(resource: PermissionResource, permissionSet: Set<string>): AccessValue {
  const orderedOptions = [...resource.options].reverse()
  for (const option of orderedOptions) {
    if (option.scopes.every((scope) => permissionSet.has(scope))) {
      return option.value
    }
  }
  return "none"
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
  const permissionSet = useMemo(() => new Set(form.permissions), [form.permissions])
  const activeResourceCount = useMemo(
    () => PERMISSION_RESOURCES.filter((resource) => resolveResourceAccess(resource, permissionSet) !== "none").length,
    [permissionSet]
  )
  const extraScopes = useMemo(
    () => form.permissions.filter((scope) => !KNOWN_SCOPES.has(scope)).sort((a, b) => a.localeCompare(b)),
    [form.permissions]
  )

  const updateResourceAccess = (resource: PermissionResource, nextValue: AccessValue) => {
    const resourceScopes = getResourceScopes(resource)
    const preserved = form.permissions.filter((scope) => !resourceScopes.has(scope))
    const nextScopes =
      nextValue === "none"
        ? []
        : resource.options.find((option) => option.value === nextValue)?.scopes ?? []

    onFormChange({
      ...form,
      permissions: Array.from(new Set([...preserved, ...nextScopes])).sort((a, b) => a.localeCompare(b)),
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onFormChange(EMPTY_ROLE)
        }
        onOpenChange(nextOpen)
      }}
    >
      <DialogContent
        showCloseButton={false}
        className="w-[min(980px,calc(100vw-2rem))] max-w-[min(980px,calc(100vw-2rem))] gap-0 overflow-hidden p-0"
      >
        <DialogHeader className="border-b border-border/60 px-6 py-5">
          <DialogTitle className="text-[1.05rem] font-semibold">
            {form.id ? "Manage permissions" : "Create role"}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground/80">
            Configure access by platform area instead of editing raw scopes directly.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[72vh] overflow-y-auto px-6 py-5">
          {form.id && assignmentCount > 0 ? (
            <div className="mb-6 flex items-start gap-3 rounded-2xl border border-orange-500/60 bg-orange-50 px-4 py-4 text-orange-700">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
              <div className="space-y-1">
                <p className="text-sm font-semibold">Changes will affect all assignments</p>
                <p className="text-sm">
                  This role is currently assigned in {assignmentCount} place{assignmentCount === 1 ? "" : "s"}.
                </p>
              </div>
            </div>
          ) : null}

          <div className="mb-6 rounded-2xl border border-border/60 bg-muted/20 p-4">
            <div className="grid gap-4 md:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Role Name</Label>
                <Input
                  value={form.name}
                  onChange={(event) => onFormChange({ ...form, name: event.target.value })}
                  placeholder="Role name"
                  className="h-10"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Description</Label>
                <Textarea
                  value={form.description}
                  onChange={(event) => onFormChange({ ...form, description: event.target.value })}
                  placeholder="Optional description"
                  className="min-h-10"
                />
              </div>
            </div>
          </div>

          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">Access by surface</p>
              <p className="text-xs text-muted-foreground/80">
                Write includes the related read access and any dependent manage scopes.
              </p>
            </div>
            <Badge variant="secondary" className="h-6 px-2.5 text-[11px]">
              {activeResourceCount} active area{activeResourceCount === 1 ? "" : "s"}
            </Badge>
          </div>

          <div className="space-y-2">
            {PERMISSION_RESOURCES.map((resource) => {
              const currentValue = resolveResourceAccess(resource, permissionSet)
              return (
                <div
                  key={resource.id}
                  className="grid items-center gap-3 rounded-2xl border border-border/50 bg-background px-4 py-3 md:grid-cols-[minmax(0,1fr)_150px]"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{resource.label}</p>
                    <p className="text-xs text-muted-foreground/75">{resource.description}</p>
                  </div>
                  <Select value={currentValue} onValueChange={(value) => updateResourceAccess(resource, value as AccessValue)}>
                    <SelectTrigger className="h-10 w-full rounded-xl bg-muted/20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None</SelectItem>
                      {resource.options.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )
            })}
          </div>

          {extraScopes.length > 0 ? (
            <div className="mt-6 rounded-2xl border border-border/60 bg-muted/15 p-4">
              <p className="text-sm font-medium text-foreground">Additional scopes</p>
              <p className="mt-1 text-xs text-muted-foreground/80">
                These existing scopes do not map cleanly to the current access matrix and will be preserved.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {extraScopes.map((scope) => (
                  <Badge key={scope} variant="outline" className="font-mono text-[11px]">
                    {scope}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter className="border-t border-border/60 bg-background px-6 py-4 sm:justify-between">
          <p className="hidden text-xs text-muted-foreground/70 sm:block">
            {form.id ? `Editing ${form.name || "role"}` : "Create a role and configure access."}
          </p>
          <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={saving || !form.name.trim()} className="min-w-32">
              {saving ? "Saving..." : form.id ? "Save changes" : "Create role"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
