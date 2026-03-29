"use client"

import { useEffect, useState, useCallback } from "react"
import { promptsService } from "@/services/prompts"
import type { PromptRecord } from "@/services/prompts"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { SearchInput } from "@/components/ui/search-input"
import {
  BookOpen,
  Plus,
  Trash2,
  Loader2,
  MoreHorizontal,
  Archive,
  RotateCcw,
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
import { PromptModal } from "@/components/shared/PromptModal"
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

/* ───────────────────────────── Page ───────────────────────────── */

export default function PromptLibraryPage() {
  const [prompts, setPrompts] = useState<PromptRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [section, setSection] = useState<PromptSection>("all")

  // Detail modal
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

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

  /* ── Open detail modal ── */
  const openDetail = useCallback((prompt: PromptRecord) => {
    setSelectedPromptId(prompt.id)
    setModalOpen(true)
  }, [])

  /* ── Archive / Restore ── */
  const handleArchive = useCallback(
    async (prompt: PromptRecord) => {
      try {
        await promptsService.archivePrompt(prompt.id)
        fetchPrompts()
      } catch {
        //
      }
    },
    [fetchPrompts]
  )

  const handleRestore = useCallback(
    async (prompt: PromptRecord) => {
      try {
        await promptsService.restorePrompt(prompt.id)
        fetchPrompts()
      } catch {
        //
      }
    },
    [fetchPrompts]
  )

  /* ── Delete ── */
  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await promptsService.deletePrompt(deleteTarget.id)
      setDeleteTarget(null)
      if (selectedPromptId === deleteTarget.id) {
        setModalOpen(false)
        setSelectedPromptId(null)
      }
      fetchPrompts()
    } catch (err: any) {
      setDeleteError(String(err?.message || err))
    } finally {
      setDeleting(false)
    }
  }, [deleteTarget, fetchPrompts, selectedPromptId])

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
        <Button size="sm" className="gap-1.5" onClick={() => { setSelectedPromptId(null); setModalOpen(true) }}>
          <Plus className="h-3.5 w-3.5" />
          New Prompt
        </Button>
      </AdminPageHeader>

      {/* Toolbar: Search + Tabs */}
      <div className="flex items-center justify-between gap-4 px-2 py-3 shrink-0">
        <SearchInput
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search prompts..."
          wrapperClassName="w-64"
        />
        <div className="flex items-center gap-1 rounded-lg bg-muted/50 p-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => setSection(item.key)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                section === item.key
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto bg-muted/60 mx-1 mb-2 mr-3 rounded-2xl">
        {/* Prompt grid */}
        <div className="px-4 pb-4 pt-4">
          {loading && prompts.length === 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-[200px] w-full rounded-xl" />
              ))}
            </div>
          ) : prompts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
                <BookOpen className="h-6 w-6 text-muted-foreground/40" />
              </div>
              <h3 className="text-sm font-medium text-foreground mb-1">
                {searchQuery ? "No prompts match your search" : "No prompts yet"}
              </h3>
              <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
                {searchQuery
                  ? "Try a different search term."
                  : "Create your first reusable prompt to get started."}
              </p>
              {!searchQuery && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  onClick={() => { setSelectedPromptId(null); setModalOpen(true) }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Create Prompt
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {prompts.map((prompt) => {
                  const statusConf = STATUS_CONFIG[prompt.status] || STATUS_CONFIG.active
                  return (
                    <div
                      key={prompt.id}
                      onClick={() => openDetail(prompt)}
                      className="group relative flex min-h-[200px] flex-col justify-between bg-background rounded-xl p-5 cursor-pointer transition-all duration-200 hover:ring-1 hover:ring-primary/20 overflow-hidden"
                    >
                      {/* Header */}
                      <div className="flex items-center justify-between relative z-10">
                        <div className="flex items-center gap-2">
                          <div className={cn("h-2 w-2 rounded-full", statusConf.color)} />
                          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                            {statusConf.label}
                          </span>
                        </div>
                        <div
                          className="opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-6 w-6 -mr-1">
                                <MoreHorizontal className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-44">
                              {prompt.status === "active" ? (
                                <DropdownMenuItem onClick={() => handleArchive(prompt)}>
                                  <Archive className="h-3.5 w-3.5 mr-2" />
                                  Archive
                                </DropdownMenuItem>
                              ) : (
                                <DropdownMenuItem onClick={() => handleRestore(prompt)}>
                                  <RotateCcw className="h-3.5 w-3.5 mr-2" />
                                  Restore
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => setDeleteTarget(prompt)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-3.5 w-3.5 mr-2" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>

                      {/* Content */}
                      <div className="relative z-10 my-2 flex-1">
                        <h3 className="text-base font-bold tracking-tight text-foreground truncate group-hover:text-primary transition-colors">
                          {prompt.name}
                        </h3>
                        {prompt.tags && prompt.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {prompt.tags.slice(0, 3).map((tag) => (
                              <span
                                key={tag}
                                className="text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded"
                              >
                                {tag}
                              </span>
                            ))}
                            {prompt.tags.length > 3 && (
                              <span className="text-[10px] text-muted-foreground">
                                +{prompt.tags.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground mt-2 line-clamp-3 leading-relaxed font-mono">
                          {prompt.content || "No content yet."}
                        </p>
                      </div>

                      {/* Footer */}
                      <div className="flex items-center justify-between relative z-10 pt-2 border-t border-border/30">
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span className="font-mono">v{prompt.version}</span>
                          <span className="text-border">|</span>
                          <span>{prompt.scope}</span>
                        </div>
                        <BookOpen className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary/60 transition-colors" />
                      </div>
                    </div>
                  )
                })}
              </div>
              {total > 0 && (
                <p className="text-xs text-muted-foreground pt-4 px-1">
                  {total} prompt{total !== 1 ? "s" : ""} total
                </p>
              )}
            </>
          )}
        </div>
      </div>

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

      <PromptModal
        promptId={selectedPromptId}
        open={modalOpen}
        onOpenChange={setModalOpen}
        onPromptUpdated={() => {
          void fetchPrompts()
        }}
      />
    </div>
  )
}
