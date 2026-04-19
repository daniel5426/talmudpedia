"use client"

import { useEffect, useState } from "react"
import {
  AlertCircle,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  Trash2,
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
import { formatHttpErrorMessage } from "@/services/http"
import {
  settingsApiKeysService,
  settingsProjectsService,
  SettingsApiKey,
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

export function ApiKeysSection() {
  const [scope, setScope] = useState<"organization" | "project">("organization")
  const [projects, setProjects] = useState<SettingsProject[]>([])
  const [projectSlug, setProjectSlug] = useState("")
  const [items, setItems] = useState<SettingsApiKey[]>([])
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Create modal
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createScope, setCreateScope] = useState<"organization" | "project">("organization")
  const [createProjectSlug, setCreateProjectSlug] = useState("")
  const [creating, setCreating] = useState(false)

  // Load projects list
  useEffect(() => {
    void settingsProjectsService.listProjects().then((data) => {
      setProjects(data)
      if (!projectSlug && data[0]) setProjectSlug(data[0].slug)
    })
  }, [])

  // Load API keys when scope/project changes
  const loadKeys = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await settingsApiKeysService.listApiKeys({
        owner_scope: scope,
        project_slug: scope === "project" ? projectSlug : undefined,
      })
      setItems(data)
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to load API keys."))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (scope === "project" && !projectSlug) return
    void loadKeys()
  }, [scope, projectSlug])

  const createKey = async () => {
    if (!createName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const created = await settingsApiKeysService.createApiKey({
        owner_scope: createScope,
        project_slug: createScope === "project" ? createProjectSlug : undefined,
        name: createName.trim(),
      })
      setToken(created.token)
      setCreateName("")
      setCreateOpen(false)
      // Switch view to match what was just created
      setScope(createScope)
      if (createScope === "project") setProjectSlug(createProjectSlug)
      await loadKeys()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to create API key."))
    } finally {
      setCreating(false)
    }
  }

  const revokeKey = async (keyId: string) => {
    try {
      await settingsApiKeysService.revokeApiKey(keyId, {
        owner_scope: scope,
        project_slug: scope === "project" ? projectSlug : undefined,
      })
      await loadKeys()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to revoke API key."))
    }
  }

  const deleteKey = async (keyId: string) => {
    try {
      await settingsApiKeysService.deleteApiKey(keyId, {
        owner_scope: scope,
        project_slug: scope === "project" ? projectSlug : undefined,
      })
      await loadKeys()
    } catch (error) {
      setError(formatHttpErrorMessage(error, "Failed to delete API key."))
    }
  }

  const filteredItems = search.trim()
    ? items.filter(
        (item) =>
          item.name.toLowerCase().includes(search.toLowerCase()) ||
          item.key_prefix.toLowerCase().includes(search.toLowerCase())
      )
    : items

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div>
        <h2 className="text-sm font-medium text-foreground">API Keys</h2>
        <p className="text-xs text-muted-foreground/70 mt-0.5">
          Manage organization and project API keys. Secrets are shown only once at creation.
        </p>
      </div>

      {/* ── Toolbar: search + scope filter ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <SearchInput
          placeholder="Search keys…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          wrapperClassName="w-56"
        />
        <Select value={scope} onValueChange={(value) => setScope(value as "organization" | "project")}>
          <SelectTrigger className="h-8 w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="organization">Organization</SelectItem>
            <SelectItem value="project">Project</SelectItem>
          </SelectContent>
        </Select>
        {scope === "project" && (
          <Select
            value={projectSlug || "__none__"}
            onValueChange={(value) => setProjectSlug(value === "__none__" ? "" : value)}
          >
            <SelectTrigger className="h-8 w-[180px]">
              <SelectValue placeholder="Project" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Select project</SelectItem>
              {projects.map((project) => (
                <SelectItem key={project.id} value={project.slug}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <div className="flex-1" />

        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs shrink-0"
          onClick={() => { setCreateScope(scope); setCreateProjectSlug(projectSlug); setCreateOpen(true) }}
        >
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          New API Key
        </Button>
      </div>

      {/* ── Token reveal banner ── */}
      {token && (
        <div className="rounded-lg border border-border/60 bg-muted/30 px-4 py-3">
          <p className="mb-2 text-xs text-muted-foreground">
            Copy this secret now — it will not be shown again.
          </p>
          <div className="flex gap-2">
            <Input value={token} readOnly className="h-8 font-mono text-xs flex-1" />
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => void navigator.clipboard.writeText(token)}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      <ErrorBanner message={error} />

      {/* ── Key list ── */}
      {loading ? (
        <p className="text-xs text-muted-foreground py-8 text-center">Loading API keys…</p>
      ) : filteredItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <KeyRound className="h-8 w-8 text-muted-foreground/30 mb-3" />
          <p className="text-sm font-medium text-muted-foreground">
            {search ? "No keys found" : "No API keys yet"}
          </p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            {search ? "Try a different search term" : "Create your first API key to get started"}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-border/30">
          {filteredItems.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between px-1 py-2.5 hover:bg-muted/20 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{item.name}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        item.status === "active" ? "bg-emerald-500" : "bg-zinc-400"
                      }`}
                    />
                    <span className="text-xs text-muted-foreground/60">{item.status}</span>
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground/50">{item.key_prefix}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => revokeKey(item.id)}
                  disabled={item.status !== "active"}
                >
                  Revoke
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive h-7 text-xs"
                  onClick={() => deleteKey(item.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Create API Key Modal ── */}
      <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setCreateName("") }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base">New API Key</DialogTitle>
            <DialogDescription className="text-xs">
              Create a new API key for authentication. The secret will be shown only once.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Name</Label>
              <Input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="My API Key"
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Scope</Label>
              <Select value={createScope} onValueChange={(value) => setCreateScope(value as "organization" | "project")}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="organization">Organization</SelectItem>
                  <SelectItem value="project">Project</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {createScope === "project" && (
              <div className="space-y-1.5">
                <Label className="text-xs">Project</Label>
                <Select
                  value={createProjectSlug || "__none__"}
                  onValueChange={(value) => setCreateProjectSlug(value === "__none__" ? "" : value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Select project</SelectItem>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={project.slug}>{project.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={createKey} disabled={creating || !createName.trim()}>
                {creating && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Create Key
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
