"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { FolderOpen, Plus, RefreshCw } from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { fileSpacesService, type FileSpace } from "@/services"

function FileSpaceSkeleton() {
  return (
    <div className="rounded-xl border border-border/60 bg-card p-5 space-y-3">
      <Skeleton className="h-4 w-36" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  )
}

export default function FilesPage() {
  const [spaces, setSpaces] = useState<FileSpace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  async function loadSpaces() {
    try {
      setLoading(true)
      const response = await fileSpacesService.list()
      setSpaces(response.items)
      setError(null)
    } catch (err) {
      console.error(err)
      setError("Failed to load file spaces.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSpaces()
  }, [])

  async function handleCreate() {
    if (!name.trim()) return
    try {
      setSubmitting(true)
      await fileSpacesService.create({ name: name.trim(), description: description.trim() || null })
      setName("")
      setDescription("")
      setOpen(false)
      await loadSpaces()
    } catch (err) {
      console.error(err)
      setError("Failed to create file space.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-screen w-full flex-col bg-background">
      <AdminPageHeader>
        <CustomBreadcrumb items={[{ label: "Files", href: "/admin/files", active: true }]} />
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadSpaces} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" />
                New File Space
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create File Space</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <Input placeholder="Research Workspace" value={name} onChange={(e) => setName(e.target.value)} />
                <Textarea
                  placeholder="Optional description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                <Button onClick={handleCreate} disabled={submitting || !name.trim()}>
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </AdminPageHeader>

      <main className="flex-1 overflow-y-auto p-4" data-admin-page-scroll>
        {error ? (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <FileSpaceSkeleton key={index} />
            ))}
          </div>
        ) : spaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/70 px-6 py-24 text-center">
            <FolderOpen className="mb-4 h-10 w-10 text-muted-foreground/60" />
            <h2 className="text-lg font-semibold">No file spaces yet</h2>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Create a durable workspace and link it to workflows that need shared files.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {spaces.map((space) => (
              <Link
                key={space.id}
                href={`/admin/files/${space.id}`}
                className="rounded-xl border border-border/60 bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/20"
              >
                <div className="flex items-start gap-3">
                  <div className="rounded-lg border border-border/70 bg-background p-2">
                    <FolderOpen className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold">{space.name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {space.description || "No description"}
                    </div>
                    <div className="mt-3 text-[11px] text-muted-foreground">
                      Updated {space.updated_at ? new Date(space.updated_at).toLocaleString() : "unknown"}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
