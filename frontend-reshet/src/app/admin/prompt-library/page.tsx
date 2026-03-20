"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import { promptsService } from "@/services/prompts"
import type {
  PromptRecord,
  PromptVersionRecord,
  PromptUsageRecord,
  CreatePromptRequest,
} from "@/services/prompts"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  BookOpen,
  Plus,
  Trash2,
  Loader2,
  Search,
  MoreHorizontal,
  Archive,
  RotateCcw,
  Clock,
  Activity,
  ChevronRight,
  X,
  History,
  Link2,
  Bot,
  Wrench,
  Package,
} from "lucide-react"
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

/* ───────────────────────────── Constants ───────────────────────────── */

type PromptSection = "all" | "active" | "archived"

const NAV_ITEMS: Array<{ key: PromptSection; label: string }> = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "archived", label: "Archived" },
]

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  active: { color: "bg-emerald-500", label: "Active" },
  archived: { color: "bg-zinc-400", label: "Archived" },
}

const RESOURCE_ICONS: Record<string, React.JSX.Element> = {
  agent: <Bot className="h-3.5 w-3.5" />,
  tool: <Wrench className="h-3.5 w-3.5" />,
  artifact: <Package className="h-3.5 w-3.5" />,
}

/* ───────────────────────────── Page ───────────────────────────── */

export default function PromptLibraryPage() {
  const [prompts, setPrompts] = useState<PromptRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [section, setSection] = useState<PromptSection>("all")

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState<CreatePromptRequest>({ name: "", content: "" })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Detail sheet
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRecord | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [sheetTab, setSheetTab] = useState<"details" | "versions" | "usage">("details")

  // Detail editing
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editContent, setEditContent] = useState("")
  const [editSurfaces, setEditSurfaces] = useState("")
  const [editTags, setEditTags] = useState("")
  const [editDirty, setEditDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Versions
  const [versions, setVersions] = useState<PromptVersionRecord[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [rollingBack, setRollingBack] = useState(false)

  // Usage
  const [usage, setUsage] = useState<PromptUsageRecord[]>([])
  const [usageLoading, setUsageLoading] = useState(false)

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<PromptRecord | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  /* ── Fetch list ── */
  const fetchPrompts = useCallback(async () => {
    setLoading(true)
    try {
      const statusParam = section === "all" ? undefined : section
      const resp = await promptsService.listPrompts({
        q: searchQuery || undefined,
        status: statusParam,
        limit: 200,
      })
      setPrompts(resp.prompts)
      setTotal(resp.total)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [searchQuery, section])

  useEffect(() => {
    fetchPrompts()
  }, [fetchPrompts])

  /* ── Create ── */
  const handleCreate = useCallback(async () => {
    if (!createForm.name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      await promptsService.createPrompt(createForm)
      setCreateOpen(false)
      setCreateForm({ name: "", content: "" })
      fetchPrompts()
    } catch (err: any) {
      setCreateError(String(err?.message || err))
    } finally {
      setCreating(false)
    }
  }, [createForm, fetchPrompts])

  /* ── Open detail sheet ── */
  const openDetail = useCallback(async (prompt: PromptRecord) => {
    setSelectedPrompt(prompt)
    setEditName(prompt.name)
    setEditDescription(prompt.description || "")
    setEditContent(prompt.content)
    setEditSurfaces((prompt.allowed_surfaces || []).join(", "))
    setEditTags((prompt.tags || []).join(", "))
    setEditDirty(false)
    setSaveError(null)
    setSheetTab("details")
    setSheetOpen(true)
  }, [])

  /* ── Save edits ── */
  const handleSave = useCallback(async () => {
    if (!selectedPrompt) return
    setSaving(true)
    setSaveError(null)
    try {
      const surfaces = editSurfaces
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
      const tags = editTags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
      const updated = await promptsService.updatePrompt(selectedPrompt.id, {
        name: editName !== selectedPrompt.name ? editName : undefined,
        description: editDescription !== (selectedPrompt.description || "") ? editDescription : undefined,
        content: editContent !== selectedPrompt.content ? editContent : undefined,
        allowed_surfaces: surfaces,
        tags,
      })
      setSelectedPrompt(updated)
      setEditDirty(false)
      fetchPrompts()
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }, [selectedPrompt, editName, editDescription, editContent, editSurfaces, editTags, fetchPrompts])

  /* ── Versions ── */
  const fetchVersions = useCallback(async () => {
    if (!selectedPrompt) return
    setVersionsLoading(true)
    try {
      const v = await promptsService.listVersions(selectedPrompt.id)
      setVersions(v)
    } catch {
      //
    } finally {
      setVersionsLoading(false)
    }
  }, [selectedPrompt])

  useEffect(() => {
    if (sheetTab === "versions" && selectedPrompt) {
      fetchVersions()
    }
  }, [sheetTab, selectedPrompt, fetchVersions])

  const handleRollback = useCallback(
    async (version: number) => {
      if (!selectedPrompt) return
      setRollingBack(true)
      try {
        const updated = await promptsService.rollback(selectedPrompt.id, version)
        setSelectedPrompt(updated)
        setEditName(updated.name)
        setEditDescription(updated.description || "")
        setEditContent(updated.content)
        setEditDirty(false)
        fetchVersions()
        fetchPrompts()
      } catch {
        //
      } finally {
        setRollingBack(false)
      }
    },
    [selectedPrompt, fetchVersions, fetchPrompts]
  )

  /* ── Usage ── */
  const fetchUsage = useCallback(async () => {
    if (!selectedPrompt) return
    setUsageLoading(true)
    try {
      const u = await promptsService.getUsage(selectedPrompt.id)
      setUsage(u)
    } catch {
      //
    } finally {
      setUsageLoading(false)
    }
  }, [selectedPrompt])

  useEffect(() => {
    if (sheetTab === "usage" && selectedPrompt) {
      fetchUsage()
    }
  }, [sheetTab, selectedPrompt, fetchUsage])

  /* ── Archive / Restore ── */
  const handleArchive = useCallback(
    async (prompt: PromptRecord) => {
      try {
        await promptsService.archivePrompt(prompt.id)
        fetchPrompts()
        if (selectedPrompt?.id === prompt.id) {
          const updated = await promptsService.getPrompt(prompt.id)
          setSelectedPrompt(updated)
        }
      } catch {
        //
      }
    },
    [fetchPrompts, selectedPrompt]
  )

  const handleRestore = useCallback(
    async (prompt: PromptRecord) => {
      try {
        await promptsService.restorePrompt(prompt.id)
        fetchPrompts()
        if (selectedPrompt?.id === prompt.id) {
          const updated = await promptsService.getPrompt(prompt.id)
          setSelectedPrompt(updated)
        }
      } catch {
        //
      }
    },
    [fetchPrompts, selectedPrompt]
  )

  /* ── Delete ── */
  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await promptsService.deletePrompt(deleteTarget.id)
      setDeleteTarget(null)
      if (selectedPrompt?.id === deleteTarget.id) {
        setSheetOpen(false)
        setSelectedPrompt(null)
      }
      fetchPrompts()
    } catch (err: any) {
      setDeleteError(String(err?.message || err))
    } finally {
      setDeleting(false)
    }
  }, [deleteTarget, selectedPrompt, fetchPrompts])

  /* ── Render ── */
  return (
    <div className="flex h-full w-full flex-col">
      {/* Header */}
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Agents Management", href: "/admin/agents" },
            { label: "Prompt Library", active: true },
          ]}
        />
        <Button size="sm" className="gap-1.5" onClick={() => setCreateOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          New Prompt
        </Button>
      </AdminPageHeader>

      {/* Content */}
      <div className="flex flex-1 min-h-0">
        {/* Left nav */}
        <div className="w-48 shrink-0 border-r p-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => setSection(item.key)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                section === item.key
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Main area */}
        <div className="flex-1 w-full flex flex-col min-h-0 overflow-auto p-4 space-y-4">
          {/* Search */}
          <div className="relative max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search prompts..."
              className="pl-8 h-8 text-sm"
            />
          </div>

          {/* Prompt list */}
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : prompts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <BookOpen className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">No prompts found</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3 gap-1.5"
                onClick={() => setCreateOpen(true)}
              >
                <Plus className="h-3.5 w-3.5" />
                Create your first prompt
              </Button>
            </div>
          ) : (
            <div className="space-y-1">
              {prompts.map((prompt) => {
                const statusConf = STATUS_CONFIG[prompt.status] || STATUS_CONFIG.active
                return (
                  <div
                    key={prompt.id}
                    onClick={() => openDetail(prompt)}
                    className={cn(
                      "group flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors",
                      "hover:bg-muted/60",
                      selectedPrompt?.id === prompt.id && sheetOpen && "bg-muted/60 border-primary/20"
                    )}
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-100 dark:bg-blue-900/30">
                      <BookOpen className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">{prompt.name}</span>
                        <div className="flex items-center gap-1">
                          <span className={cn("h-1.5 w-1.5 rounded-full", statusConf.color)} />
                          <span className="text-[10px] text-muted-foreground">{statusConf.label}</span>
                        </div>
                      </div>
                      {prompt.description && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {prompt.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] text-muted-foreground">v{prompt.version}</span>
                      <span className="text-[10px] text-muted-foreground">{prompt.scope}</span>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          {prompt.status === "active" ? (
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation()
                                handleArchive(prompt)
                              }}
                            >
                              <Archive className="h-3.5 w-3.5 mr-2" />
                              Archive
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation()
                                handleRestore(prompt)
                              }}
                            >
                              <RotateCcw className="h-3.5 w-3.5 mr-2" />
                              Restore
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteTarget(prompt)
                            }}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                      <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {!loading && total > 0 && (
            <p className="text-xs text-muted-foreground pt-2">
              {total} prompt{total !== 1 ? "s" : ""} total
            </p>
          )}
        </div>
      </div>

      {/* ── Create Dialog ── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create Prompt</DialogTitle>
            <DialogDescription>
              Add a new reusable prompt to the library.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Name</Label>
              <Input
                value={createForm.name}
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Customer Support Tone"
                className="h-8 text-sm"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Description</Label>
              <Input
                value={createForm.description || ""}
                onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Content</Label>
              <Textarea
                value={createForm.content || ""}
                onChange={(e) => setCreateForm((f) => ({ ...f, content: e.target.value }))}
                placeholder="Write the prompt content..."
                rows={4}
                className="text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Allowed Surfaces</Label>
              <Input
                value={(createForm.allowed_surfaces || []).join(", ")}
                onChange={(e) =>
                  setCreateForm((f) => ({
                    ...f,
                    allowed_surfaces: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="Leave empty for all surfaces"
                className="h-8 text-sm"
              />
              <p className="text-[10px] text-muted-foreground">
                Comma-separated. e.g. agent.instructions, llm.system_prompt
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Tags</Label>
              <Input
                value={(createForm.tags || []).join(", ")}
                onChange={(e) =>
                  setCreateForm((f) => ({
                    ...f,
                    tags: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="Optional tags"
                className="h-8 text-sm"
              />
            </div>
            {createError && (
              <div className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
                {createError}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={creating || !createForm.name.trim()}
              className="gap-1.5"
            >
              {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Dialog ── */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Prompt</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
              This cannot be undone. Prompts that are still referenced cannot be deleted.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <div className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
              {deleteError}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDelete}
              disabled={deleting}
              className="gap-1.5"
            >
              {deleting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Detail Sheet ── */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="sm:max-w-lg overflow-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-blue-500" />
              {selectedPrompt?.name || "Prompt"}
            </SheetTitle>
            <SheetDescription>
              {selectedPrompt
                ? `Version ${selectedPrompt.version} · ${selectedPrompt.scope} · ${selectedPrompt.status}`
                : ""}
            </SheetDescription>
          </SheetHeader>

          {selectedPrompt && (
            <Tabs
              value={sheetTab}
              onValueChange={(v) => setSheetTab(v as typeof sheetTab)}
              className="mt-4"
            >
              <TabsList className="w-full">
                <TabsTrigger value="details" className="flex-1 gap-1.5 text-xs">
                  <BookOpen className="h-3 w-3" />
                  Details
                </TabsTrigger>
                <TabsTrigger value="versions" className="flex-1 gap-1.5 text-xs">
                  <History className="h-3 w-3" />
                  Versions
                </TabsTrigger>
                <TabsTrigger value="usage" className="flex-1 gap-1.5 text-xs">
                  <Link2 className="h-3 w-3" />
                  Usage
                </TabsTrigger>
              </TabsList>

              {/* ── Details Tab ── */}
              <TabsContent value="details" className="space-y-4 mt-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Name</Label>
                  <Input
                    value={editName}
                    onChange={(e) => { setEditName(e.target.value); setEditDirty(true) }}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Description</Label>
                  <Input
                    value={editDescription}
                    onChange={(e) => { setEditDescription(e.target.value); setEditDirty(true) }}
                    placeholder="Optional description"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Content</Label>
                  <Textarea
                    value={editContent}
                    onChange={(e) => { setEditContent(e.target.value); setEditDirty(true) }}
                    rows={8}
                    className="text-sm font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Allowed Surfaces</Label>
                  <Input
                    value={editSurfaces}
                    onChange={(e) => { setEditSurfaces(e.target.value); setEditDirty(true) }}
                    placeholder="Leave empty for all"
                    className="h-8 text-sm"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Comma-separated surface keys
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Tags</Label>
                  <Input
                    value={editTags}
                    onChange={(e) => { setEditTags(e.target.value); setEditDirty(true) }}
                    placeholder="Optional tags"
                    className="h-8 text-sm"
                  />
                </div>
                {saveError && (
                  <div className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
                    {saveError}
                  </div>
                )}
                <div className="flex items-center gap-2 pt-2">
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={!editDirty || saving}
                    className="gap-1.5"
                  >
                    {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Save
                  </Button>
                  {selectedPrompt.status === "active" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleArchive(selectedPrompt)}
                      className="gap-1.5"
                    >
                      <Archive className="h-3.5 w-3.5" />
                      Archive
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRestore(selectedPrompt)}
                      className="gap-1.5"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      Restore
                    </Button>
                  )}
                </div>
              </TabsContent>

              {/* ── Versions Tab ── */}
              <TabsContent value="versions" className="mt-4">
                {versionsLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-14 w-full rounded-lg" />
                    ))}
                  </div>
                ) : versions.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    No version history found
                  </p>
                ) : (
                  <div className="space-y-2">
                    {versions.map((v) => (
                      <div
                        key={v.id}
                        className="flex items-start gap-3 rounded-lg border p-3"
                      >
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-xs font-mono font-medium">
                          v{v.version}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{v.name}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {new Date(v.created_at).toLocaleString()}
                          </p>
                          {v.content && (
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2 font-mono">
                              {v.content.slice(0, 120)}{v.content.length > 120 ? "..." : ""}
                            </p>
                          )}
                        </div>
                        {v.version !== selectedPrompt.version && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleRollback(v.version)}
                            disabled={rollingBack}
                            className="gap-1 shrink-0 text-xs"
                          >
                            {rollingBack ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <RotateCcw className="h-3 w-3" />
                            )}
                            Rollback
                          </Button>
                        )}
                        {v.version === selectedPrompt.version && (
                          <Badge variant="secondary" className="text-[10px] shrink-0">
                            Current
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </TabsContent>

              {/* ── Usage Tab ── */}
              <TabsContent value="usage" className="mt-4">
                {usageLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-12 w-full rounded-lg" />
                    ))}
                  </div>
                ) : usage.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    This prompt is not referenced anywhere
                  </p>
                ) : (
                  <div className="space-y-2">
                    {usage.map((u, idx) => (
                      <div
                        key={`${u.resource_type}-${u.resource_id}-${u.location_pointer}-${idx}`}
                        className="flex items-center gap-3 rounded-lg border p-3"
                      >
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
                          {RESOURCE_ICONS[u.resource_type] || <Activity className="h-3.5 w-3.5" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{u.resource_name}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <Badge variant="outline" className="text-[10px] h-4">
                              {u.resource_type}
                            </Badge>
                            <span className="text-[10px] text-muted-foreground font-mono truncate">
                              {u.surface}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
