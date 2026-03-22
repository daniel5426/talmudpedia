"use client"

import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  Archive,
  Bot,
  ChevronDown,
  FileDown,
  History,
  Link2,
  Loader2,
  Package,
  RotateCcw,
  Save,
  Wrench,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { promptsService, type PromptRecord, type PromptUsageRecord, type PromptVersionRecord } from "@/services/prompts"
import { cn } from "@/lib/utils"

interface PromptModalProps {
  promptId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onFill?: (promptId: string, content: string) => void
  onPromptUpdated?: (prompt: PromptRecord) => void
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  active: { color: "bg-emerald-500", label: "Active" },
  archived: { color: "bg-zinc-400", label: "Archived" },
}

const RESOURCE_ICONS: Record<string, React.JSX.Element> = {
  agent: <Bot className="h-3.5 w-3.5" />,
  tool: <Wrench className="h-3.5 w-3.5" />,
  artifact: <Package className="h-3.5 w-3.5" />,
}

export function PromptModal({
  promptId,
  open,
  onOpenChange,
  onFill,
  onPromptUpdated,
}: PromptModalProps) {
  const [prompt, setPrompt] = useState<PromptRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [showMoreFields, setShowMoreFields] = useState(false)

  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editContent, setEditContent] = useState("")
  const [editSurfaces, setEditSurfaces] = useState("")
  const [editTagsArray, setEditTagsArray] = useState<string[]>([])
  const [tagInput, setTagInput] = useState("")
  const [editDirty, setEditDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [versions, setVersions] = useState<PromptVersionRecord[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [rollingBack, setRollingBack] = useState(false)

  const [usage, setUsage] = useState<PromptUsageRecord[]>([])
  const [usageLoading, setUsageLoading] = useState(false)
  const [usageOpen, setUsageOpen] = useState(false)

  const hydratePrompt = useCallback((nextPrompt: PromptRecord) => {
    setPrompt(nextPrompt)
    setEditName(nextPrompt.name)
    setEditDescription(nextPrompt.description || "")
    setEditContent(nextPrompt.content)
    setEditSurfaces((nextPrompt.allowed_surfaces || []).join(", "))
    setEditTagsArray(nextPrompt.tags || [])
    setTagInput("")
    setEditDirty(false)
    setSaveError(null)
  }, [])

  const refreshPrompt = useCallback(async () => {
    if (!promptId) return
    setLoading(true)
    try {
      const nextPrompt = await promptsService.getPrompt(promptId)
      hydratePrompt(nextPrompt)
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    } finally {
      setLoading(false)
    }
  }, [hydratePrompt, promptId])

  useEffect(() => {
    if (!open) {
      setPrompt(null)
      setVersions([])
      setUsage([])
      setEditDirty(false)
      setSaveError(null)
      return
    }
    if (!promptId) {
      // Create mode — reset to blank form
      setPrompt(null)
      setEditName("")
      setEditDescription("")
      setEditContent("")
      setEditSurfaces("")
      setEditTagsArray([])
      setTagInput("")
      setEditDirty(false)
      setSaveError(null)
      return
    }
    void refreshPrompt()
  }, [open, promptId, refreshPrompt])

  useEffect(() => {
    if (!versionsOpen || !prompt?.id) return
    setVersionsLoading(true)
    promptsService
      .listVersions(prompt.id)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setVersionsLoading(false))
  }, [versionsOpen, prompt?.id])

  useEffect(() => {
    if (!usageOpen || !prompt?.id) return
    setUsageLoading(true)
    promptsService
      .getUsage(prompt.id)
      .then(setUsage)
      .catch(() => setUsage([]))
      .finally(() => setUsageLoading(false))
  }, [usageOpen, prompt?.id])

  const commitUpdatedPrompt = useCallback((nextPrompt: PromptRecord) => {
    hydratePrompt(nextPrompt)
    onPromptUpdated?.(nextPrompt)
  }, [hydratePrompt, onPromptUpdated])

  const handleSave = useCallback(async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const surfaces = editSurfaces
        .split(",")
        .map((surface) => surface.trim())
        .filter(Boolean)
      if (!prompt) {
        // Create mode
        const nextPrompt = await promptsService.createPrompt({
          name: editName,
          description: editDescription || undefined,
          content: editContent,
          allowed_surfaces: surfaces.length ? surfaces : undefined,
          tags: editTagsArray.length ? editTagsArray : undefined,
        })
        onPromptUpdated?.(nextPrompt)
        onOpenChange(false)
      } else {
        const nextPrompt = await promptsService.updatePrompt(prompt.id, {
          name: editName !== prompt.name ? editName : undefined,
          description: editDescription !== (prompt.description || "") ? editDescription : undefined,
          content: editContent !== prompt.content ? editContent : undefined,
          allowed_surfaces: surfaces,
          tags: editTagsArray,
        })
        commitUpdatedPrompt(nextPrompt)
      }
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }, [commitUpdatedPrompt, editContent, editDescription, editName, editSurfaces, editTagsArray, onOpenChange, onPromptUpdated, prompt])

  const handleArchiveToggle = useCallback(async () => {
    if (!prompt) return
    try {
      const nextPrompt =
        prompt.status === "active"
          ? await promptsService.archivePrompt(prompt.id)
          : await promptsService.restorePrompt(prompt.id)
      commitUpdatedPrompt(nextPrompt)
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    }
  }, [commitUpdatedPrompt, prompt])

  const handleRollback = useCallback(async (version: number) => {
    if (!prompt) return
    setRollingBack(true)
    try {
      const nextPrompt = await promptsService.rollback(prompt.id, version)
      commitUpdatedPrompt(nextPrompt)
      const nextVersions = await promptsService.listVersions(prompt.id)
      setVersions(nextVersions)
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    } finally {
      setRollingBack(false)
    }
  }, [commitUpdatedPrompt, prompt])

  const handleFill = useCallback(async () => {
    if (!promptId || !onFill) return
    try {
      const latest = await promptsService.getPrompt(promptId)
      onFill(promptId, latest.content)
      onOpenChange(false)
    } catch (err: any) {
      setSaveError(String(err?.message || err))
    }
  }, [onFill, onOpenChange, promptId])

  const isCreateMode = !promptId
  const canSave = isCreateMode ? editName.trim().length > 0 : editDirty

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="!max-w-[50rem] h-[80vh] flex flex-col p-0 gap-0 overflow-hidden border-0 shadow-none ring-0">
        <DialogTitle className="sr-only">
          {isCreateMode ? "New Prompt" : (prompt?.name || "Prompt")}
        </DialogTitle>
        {loading && !isCreateMode ? (
          <div className="flex h-full flex-col">
            <div className="border-b px-5 py-4">
              <Skeleton className="h-5 w-48" />
            </div>
            <div className="flex-1 space-y-3 px-5 py-5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 pl-5 pr-2 py-2 border-b shrink-0">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <Input
                  value={editName}
                  onChange={(e) => {
                    setEditName(e.target.value)
                    setEditDirty(true)
                  }}
                  className="h-8 text-sm font-medium border-none bg-transparent px-0 focus-visible:ring-0 shadow-none"
                />
                <div className="h-4 w-px bg-border shrink-0" />
                <Input
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return
                    e.preventDefault()
                    const nextTag = tagInput.trim()
                    if (!nextTag || editTagsArray.includes(nextTag) || editTagsArray.length >= 3) {
                      return
                    }
                    setEditTagsArray([...editTagsArray, nextTag])
                    setTagInput("")
                    setEditDirty(true)
                  }}
                  placeholder={editTagsArray.length < 3 ? "Add tag…" : "Max 3 tags"}
                  disabled={editTagsArray.length >= 3}
                  className="h-8 text-xs border-none bg-transparent px-0 focus-visible:ring-0 shadow-none max-w-[140px]"
                />
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    "h-8 w-8 p-0 text-muted-foreground hover:text-foreground",
                    showMoreFields && "text-foreground bg-muted"
                  )}
                  onClick={() => setShowMoreFields((current) => !current)}
                  title="More fields"
                >
                  <ChevronDown className={cn("h-4 w-4 transition-transform", showMoreFields && "rotate-180")} />
                </Button>

                {!isCreateMode && (
                  <>
                    <DropdownMenu open={versionsOpen} onOpenChange={setVersionsOpen}>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground" title="Version history">
                          <History className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" sideOffset={10} className="w-72 rounded-md border-border/70 p-1.5 shadow-lg max-h-80 overflow-auto">
                        <div className="px-2 py-1.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                          Version History
                        </div>
                        {versionsLoading && versions.length === 0 ? (
                          <div className="space-y-1.5 p-1">
                            <Skeleton className="h-11 w-full rounded-lg" />
                            <Skeleton className="h-11 w-full rounded-lg" />
                          </div>
                        ) : null}
                        {!versionsLoading && versions.length === 0 ? (
                          <div className="px-3 py-6 text-center text-xs text-muted-foreground">No versions yet.</div>
                        ) : null}
                        {versions.map((versionRow) => (
                          <div
                            key={versionRow.id}
                            className={cn(
                              "flex items-center justify-between gap-2 rounded-md px-3 py-2 hover:bg-muted/60 transition-colors",
                              versionRow.version === prompt?.version && "bg-muted/40"
                            )}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-medium">v{versionRow.version}</span>
                                {versionRow.version === prompt?.version ? (
                                  <Badge variant="outline" className="h-4 px-1 text-[10px]">Current</Badge>
                                ) : null}
                              </div>
                              <div className="text-[10px] text-muted-foreground mt-0.5">
                                {new Date(versionRow.created_at).toLocaleString()}
                              </div>
                            </div>
                            {versionRow.version !== prompt?.version ? (
                              <Button size="sm" variant="ghost" className="h-7 text-[11px]" disabled={rollingBack} onClick={() => void handleRollback(versionRow.version)}>
                                {rollingBack ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
                                Rollback
                              </Button>
                            ) : null}
                          </div>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <DropdownMenu open={usageOpen} onOpenChange={setUsageOpen}>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground" title="Usage references">
                          <Link2 className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" sideOffset={10} className="w-72 rounded-md border-border/70 p-1.5 shadow-lg max-h-80 overflow-auto">
                        <div className="px-2 py-1.5 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                          Referenced By
                        </div>
                        {usageLoading && usage.length === 0 ? (
                          <div className="space-y-1.5 p-1">
                            <Skeleton className="h-10 w-full rounded-lg" />
                            <Skeleton className="h-10 w-full rounded-lg" />
                          </div>
                        ) : null}
                        {!usageLoading && usage.length === 0 ? (
                          <div className="px-3 py-6 text-center text-xs text-muted-foreground">Not referenced anywhere.</div>
                        ) : null}
                        {usage.map((item, idx) => (
                          <div
                            key={`${item.resource_type}-${item.resource_id}-${item.location_pointer}-${idx}`}
                            className="flex items-center gap-2.5 rounded-md px-3 py-2 hover:bg-muted/60 transition-colors"
                          >
                            <div className="flex h-6 w-6 items-center justify-center rounded bg-muted text-muted-foreground shrink-0">
                              {RESOURCE_ICONS[item.resource_type] || <Activity className="h-3 w-3" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium truncate">{item.resource_name}</div>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <Badge variant="outline" className="text-[10px] h-4 px-1">{item.resource_type}</Badge>
                                <span className="text-[10px] text-muted-foreground font-mono truncate">{item.surface}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <div className="h-4 w-px bg-border mx-1" />

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleArchiveToggle()}
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                      title={prompt?.status === "active" ? "Archive" : "Restore"}
                    >
                      {prompt?.status === "active" ? <Archive className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />}
                    </Button>
                  </>
                )}

                {onFill ? (
                  <Button size="sm" variant="outline" onClick={() => void handleFill()} className="h-6 gap-1.5 text-xs">
                    <FileDown className="h-3.5 w-3.5" />
                    Fill
                  </Button>
                ) : null}

                <Button size="sm" onClick={() => void handleSave()} disabled={!canSave || saving} className="h-6 gap-1.5 text-xs">
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Save
                </Button>

                <div className="h-4 w-px bg-border mx-0.5" />

                <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground">
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {showMoreFields ? (
              <div className="flex items-center gap-3 px-5 py-2.5 border-b bg-muted/20 shrink-0">
                <div className="flex-1 space-y-1">
                  <Label className="text-[11px] text-muted-foreground">Description</Label>
                  <Input
                    value={editDescription}
                    onChange={(e) => {
                      setEditDescription(e.target.value)
                      setEditDirty(true)
                    }}
                    placeholder="Optional description"
                    className="h-7 text-xs bg-background"
                  />
                </div>
                <div className="flex-1 space-y-1">
                  <Label className="text-[11px] text-muted-foreground">Allowed Surfaces</Label>
                  <Input
                    value={editSurfaces}
                    onChange={(e) => {
                      setEditSurfaces(e.target.value)
                      setEditDirty(true)
                    }}
                    placeholder="Leave empty for all"
                    className="h-7 text-xs bg-background"
                  />
                </div>
              </div>
            ) : null}

            {saveError ? (
              <div className="text-xs text-destructive bg-destructive/10 px-5 py-2 shrink-0">
                {saveError}
              </div>
            ) : null}

            <div className="flex-1 min-h-0 px-5">
              <Textarea
                value={editContent}
                onChange={(e) => {
                  setEditContent(e.target.value)
                  setEditDirty(true)
                }}
                placeholder="Write the prompt content..."
                className="h-full w-full resize-none text-sm font-mono border-none bg-transparent focus-visible:ring-0 shadow-none p-0"
              />
            </div>

            <div className="flex items-center justify-between px-5 py-2 border-t text-[11px] text-muted-foreground shrink-0">
              <div className="flex items-center gap-3">
                {prompt ? (
                  <>
                    <span className="font-mono">v{prompt.version}</span>
                    <span className="text-border">|</span>
                    <span>{prompt.scope}</span>
                    <span className="text-border">|</span>
                    <div className="flex items-center gap-1">
                      <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_CONFIG[prompt.status]?.color || "bg-zinc-400")} />
                      <span>{prompt.status}</span>
                    </div>
                  </>
                ) : (
                  <span className="text-muted-foreground/60">New prompt</span>
                )}
                {editTagsArray.length > 0 ? (
                  <>
                    <span className="text-border">|</span>
                    <div className="flex items-center gap-1">
                      {editTagsArray.map((tag) => (
                        <span key={tag} className="group/tag relative flex items-center gap-0.5 bg-muted rounded px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {tag}
                          <button
                            type="button"
                            onClick={() => {
                              setEditTagsArray(editTagsArray.filter((currentTag) => currentTag !== tag))
                              setEditDirty(true)
                            }}
                            className="ml-0.5 opacity-0 group-hover/tag:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                          >
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </span>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
              {editDirty ? <span className="text-primary font-medium">Unsaved changes</span> : null}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
