"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertCircle,
  FolderPlus,
  Loader2,
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
import { Textarea } from "@/components/ui/textarea"
import { formatHttpErrorMessage } from "@/services/http"
import {
  settingsProjectsService,
  SettingsProject,
} from "@/services"

function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function ProjectsSection({ onOpenAudit }: { onOpenAudit: (resourceId: string) => void }) {
  const [projects, setProjects] = useState<SettingsProject[]>([])
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ name: "", slug: "", description: "" })
  const [creating, setCreating] = useState(false)

  // Edit dialog
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState<SettingsProject | null>(null)
  const [saving, setSaving] = useState(false)

  const loadProjects = async () => {
    setLoading(true)
    try {
      const data = await settingsProjectsService.listProjects()
      setProjects(data)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to load projects."))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadProjects()
  }, [])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return projects
    return projects.filter(
      (project) =>
        project.name.toLowerCase().includes(query) || project.slug.toLowerCase().includes(query)
    )
  }, [projects, search])

  const handleCreate = async () => {
    if (!createForm.name.trim()) return
    setCreating(true)
    setError(null)
    try {
      await settingsProjectsService.createProject({
        name: createForm.name.trim(),
        slug: createForm.slug.trim() || undefined,
        description: createForm.description.trim() || undefined,
      })
      setCreateForm({ name: "", slug: "", description: "" })
      setCreateOpen(false)
      await loadProjects()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create project."))
    } finally {
      setCreating(false)
    }
  }

  const handleSave = async () => {
    if (!editForm) return
    setSaving(true)
    setError(null)
    try {
      await settingsProjectsService.updateProject(editForm.slug, {
        name: editForm.name,
        slug: editForm.slug,
        description: editForm.description,
        status: editForm.status,
      })
      setEditOpen(false)
      setEditForm(null)
      await loadProjects()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to save project."))
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (project: SettingsProject) => {
    setEditForm({ ...project })
    setEditOpen(true)
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-sm font-medium text-foreground">Projects</h2>
        <p className="text-xs text-muted-foreground/70 mt-0.5">
          Manage organization projects and their settings.
        </p>
      </div>

      {/* ── Toolbar ── */}
      <div className="flex items-center justify-between gap-3 text-xs">
        <SearchInput
          placeholder="Search projects…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          wrapperClassName="w-64"
        />
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs shrink-0"
          onClick={() => setCreateOpen(true)}
        >
          <FolderPlus className="h-3.5 w-3.5 mr-1.5" />
          New Project
        </Button>
      </div>

      <ErrorBanner message={error} />

      {/* ── Project list ── */}
      {loading ? (
        <p className="text-xs text-muted-foreground py-8 text-center">Loading…</p>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-sm font-medium text-muted-foreground">
            {search ? "No projects found" : "No projects yet"}
          </p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            {search ? "Try a different search term" : "Create your first project to get started"}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-border/30">
          {filtered.map((project) => (
            <div
              key={project.id}
              className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{project.name}</span>
                  <Badge
                    variant={project.status === "active" ? "default" : "secondary"}
                    className="text-[10px] h-4"
                  >
                    {project.status}
                  </Badge>
                </div>
                <div className="mt-0.5 flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground/50">{project.slug}</span>
                  <span className="text-muted-foreground/30">·</span>
                  <span className="text-xs text-muted-foreground/40">
                    {project.member_count} member{project.member_count !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => openEdit(project)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground"
                  onClick={() => onOpenAudit(project.id)}
                >
                  Audit
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Create Project Modal ── */}
      <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setCreateForm({ name: "", slug: "", description: "" }) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">New Project</DialogTitle>
            <DialogDescription className="text-xs">
              Create a new project in this organization.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Name</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm((c) => ({ ...c, name: e.target.value }))}
                placeholder="My Project"
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Slug</Label>
              <Input
                value={createForm.slug}
                onChange={(e) => setCreateForm((c) => ({ ...c, slug: e.target.value }))}
                placeholder="my-project (auto-generated if empty)"
                className="h-9 font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Description</Label>
              <Textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((c) => ({ ...c, description: e.target.value }))}
                placeholder="Optional description"
                className="min-h-[60px]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={handleCreate} disabled={creating || !createForm.name.trim()}>
                {creating && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Create Project
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Edit Project Modal ── */}
      <Dialog open={editOpen} onOpenChange={(open) => { setEditOpen(open); if (!open) setEditForm(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">Edit Project</DialogTitle>
            <DialogDescription className="text-xs">
              Update project details.
            </DialogDescription>
          </DialogHeader>
          {editForm && (
            <div className="space-y-4 pt-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Name</Label>
                <Input
                  value={editForm.name}
                  onChange={(e) => setEditForm((c) => c ? { ...c, name: e.target.value } : c)}
                  className="h-9"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Slug</Label>
                <Input
                  value={editForm.slug}
                  onChange={(e) => setEditForm((c) => c ? { ...c, slug: e.target.value } : c)}
                  className="h-9 font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Description</Label>
                <Textarea
                  value={editForm.description || ""}
                  onChange={(e) => setEditForm((c) => c ? { ...c, description: e.target.value } : c)}
                  className="min-h-[60px]"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Status</Label>
                <Select
                  value={editForm.status}
                  onValueChange={(value) => setEditForm((c) => c ? { ...c, status: value } : c)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={() => setEditOpen(false)}>Cancel</Button>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                  Save Changes
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
