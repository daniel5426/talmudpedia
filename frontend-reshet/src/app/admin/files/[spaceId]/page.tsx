"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import {
  Download,
  File,
  FileText,
  Folder,
  FolderPlus,
  Link2,
  RefreshCw,
  Save,
  Trash2,
  Upload,
} from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { agentService, fileSpacesService, type Agent, type FileAccessMode, type FileSpace, type FileSpaceEntry, type FileEntryRevision } from "@/services"

function TreeSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 7 }).map((_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  )
}

export default function FileSpaceDetailPage() {
  const params = useParams<{ spaceId: string }>()
  const router = useRouter()
  const uploadRef = useRef<HTMLInputElement | null>(null)
  const spaceId = String(params?.spaceId || "")

  const [space, setSpace] = useState<FileSpace | null>(null)
  const [entries, setEntries] = useState<FileSpaceEntry[]>([])
  const [links, setLinks] = useState<{ agent_id: string; access_mode: FileAccessMode }[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedRevision, setSelectedRevision] = useState<FileEntryRevision | null>(null)
  const [textDraft, setTextDraft] = useState("")
  const [saving, setSaving] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState<string>("")
  const [selectedAccessMode, setSelectedAccessMode] = useState<FileAccessMode>("read")

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.path === selectedPath) || null,
    [entries, selectedPath],
  )

  const availableAgents = useMemo(
    () => agents.filter((agent) => !links.some((link) => link.agent_id === agent.id)),
    [agents, links],
  )

  async function loadAll(nextSelectedPath?: string | null) {
    try {
      setLoading(true)
      const [spacePayload, treePayload, linksPayload, agentPayload] = await Promise.all([
        fileSpacesService.get(spaceId),
        fileSpacesService.listTree(spaceId),
        fileSpacesService.listLinks(spaceId),
        agentService.listAgents({ view: "summary", limit: 100 }),
      ])
      setSpace(spacePayload)
      setEntries(treePayload.items)
      setLinks(linksPayload.items.map((item) => ({ agent_id: item.agent_id, access_mode: item.access_mode })))
      setAgents(agentPayload.items)

      const targetPath = nextSelectedPath ?? selectedPath
      const nextEntry = treePayload.items.find((item) => item.path === targetPath) || null
      if (nextEntry?.entry_type === "file" && nextEntry.is_text) {
        const textPayload = await fileSpacesService.readText(spaceId, nextEntry.path)
        setSelectedPath(nextEntry.path)
        setSelectedRevision(textPayload.revision)
        setTextDraft(textPayload.content)
      } else {
        setSelectedPath(nextEntry?.path || null)
        setSelectedRevision(null)
        setTextDraft("")
      }
      setError(null)
    } catch (err) {
      console.error(err)
      setError("Failed to load file space.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (spaceId) {
      loadAll()
    }
  }, [spaceId])

  async function selectEntry(entry: FileSpaceEntry) {
    setSelectedPath(entry.path)
    if (entry.entry_type === "file" && entry.is_text) {
      try {
        const payload = await fileSpacesService.readText(spaceId, entry.path)
        setSelectedRevision(payload.revision)
        setTextDraft(payload.content)
      } catch (err) {
        console.error(err)
        setError("Failed to read file.")
      }
      return
    }
    setSelectedRevision(null)
    setTextDraft("")
  }

  async function handleSaveText() {
    if (!selectedEntry || selectedEntry.entry_type !== "file") return
    try {
      setSaving(true)
      const payload = await fileSpacesService.writeText(spaceId, {
        path: selectedEntry.path,
        content: textDraft,
        mime_type: selectedEntry.mime_type,
      })
      setSelectedRevision(payload.revision)
      await loadAll(selectedEntry.path)
    } catch (err) {
      console.error(err)
      setError("Failed to save file.")
    } finally {
      setSaving(false)
    }
  }

  async function handleCreateFolder() {
    const path = window.prompt("Directory path")
    if (!path) return
    try {
      await fileSpacesService.mkdir(spaceId, path)
      await loadAll()
    } catch (err) {
      console.error(err)
      setError("Failed to create directory.")
    }
  }

  async function handleDeleteSelected() {
    if (!selectedEntry) return
    if (!window.confirm(`Delete ${selectedEntry.path}?`)) return
    try {
      await fileSpacesService.deleteEntry(spaceId, selectedEntry.path)
      setSelectedPath(null)
      setSelectedRevision(null)
      setTextDraft("")
      await loadAll()
    } catch (err) {
      console.error(err)
      setError("Failed to delete entry.")
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return
    const defaultPath = selectedEntry?.entry_type === "directory"
      ? `${selectedEntry.path}/${file.name}`
      : file.name
    const path = window.prompt("Upload path", defaultPath)
    if (!path) return
    try {
      await fileSpacesService.uploadBlob(spaceId, { path, file })
      await loadAll(path)
    } catch (err) {
      console.error(err)
      setError("Failed to upload file.")
    }
  }

  async function handleCreateLink() {
    if (!selectedAgentId) return
    try {
      await fileSpacesService.upsertLink(spaceId, {
        agent_id: selectedAgentId,
        access_mode: selectedAccessMode,
      })
      setSelectedAgentId("")
      setSelectedAccessMode("read")
      await loadAll()
    } catch (err) {
      console.error(err)
      setError("Failed to link workflow.")
    }
  }

  async function handleDeleteLink(agentId: string) {
    try {
      await fileSpacesService.deleteLink(spaceId, agentId)
      await loadAll()
    } catch (err) {
      console.error(err)
      setError("Failed to unlink workflow.")
    }
  }

  async function handleArchiveSpace() {
    if (!window.confirm("Archive this file space?")) return
    try {
      await fileSpacesService.archive(spaceId)
      router.push("/admin/files")
    } catch (err) {
      console.error(err)
      setError("Failed to archive file space.")
    }
  }

  return (
    <div className="flex h-screen w-full flex-col bg-background">
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Files", href: "/admin/files" },
            { label: space?.name || "File Space", href: `/admin/files/${spaceId}`, active: true },
          ]}
        />
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => loadAll()} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleCreateFolder} disabled={loading}>
            <FolderPlus className="mr-2 h-4 w-4" />
            New Folder
          </Button>
          <input
            ref={uploadRef}
            type="file"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0] || null
              event.target.value = ""
              void handleUpload(file)
            }}
          />
          <Button variant="outline" size="sm" onClick={() => uploadRef.current?.click()} disabled={loading}>
            <Upload className="mr-2 h-4 w-4" />
            Upload
          </Button>
          <Button variant="outline" size="sm" onClick={handleArchiveSpace} disabled={loading}>
            Archive
          </Button>
        </div>
      </AdminPageHeader>

      <main className="grid flex-1 grid-cols-12 gap-4 overflow-hidden p-4" data-admin-page-scroll>
        <section className="col-span-4 flex min-h-0 flex-col rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border/70 px-4 py-3">
            <div className="text-sm font-semibold">{space?.name || "Workspace"}</div>
            <div className="text-xs text-muted-foreground">{space?.description || "No description"}</div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {loading ? (
              <TreeSkeleton />
            ) : (
              <div className="space-y-1">
                {entries.map((entry) => {
                  const Icon = entry.entry_type === "directory" ? Folder : entry.is_text ? FileText : File
                  const isSelected = entry.path === selectedPath
                  return (
                    <button
                      key={entry.id}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${
                        isSelected ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"
                      }`}
                      onClick={() => void selectEntry(entry)}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{entry.path}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        <section className="col-span-5 flex min-h-0 flex-col rounded-2xl border border-border/70 bg-card">
          <div className="border-b border-border/70 px-4 py-3">
            <div className="text-sm font-semibold">{selectedEntry?.path || "Select a file"}</div>
            <div className="text-xs text-muted-foreground">
              {selectedEntry
                ? `${selectedEntry.entry_type} ${selectedEntry.mime_type ? `• ${selectedEntry.mime_type}` : ""}`
                : "Browse the tree to inspect or edit content."}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {error ? (
              <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            ) : null}

            {!selectedEntry ? (
              <div className="text-sm text-muted-foreground">No entry selected.</div>
            ) : selectedEntry.entry_type === "directory" ? (
              <div className="space-y-3 text-sm">
                <div>This is a directory.</div>
                <div className="text-muted-foreground">Use upload or new folder actions to add content here.</div>
              </div>
            ) : selectedEntry.is_text ? (
              <div className="space-y-3">
                <Textarea
                  value={textDraft}
                  onChange={(event) => setTextDraft(event.target.value)}
                  className="min-h-[420px] font-mono text-xs"
                />
                <div className="flex items-center gap-2">
                  <Button onClick={handleSaveText} disabled={saving}>
                    <Save className="mr-2 h-4 w-4" />
                    Save
                  </Button>
                  <Button variant="outline" onClick={handleDeleteSelected}>
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-xl border border-border/70 bg-background px-4 py-3">
                  <div className="text-sm font-medium">Binary file</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Replace through upload. Download uses the current immutable revision.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <a href={fileSpacesService.buildDownloadUrl(spaceId, selectedEntry.path)} target="_blank" rel="noreferrer">
                    <Button>
                      <Download className="mr-2 h-4 w-4" />
                      Download
                    </Button>
                  </a>
                  <Button variant="outline" onClick={handleDeleteSelected}>
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </Button>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="col-span-3 flex min-h-0 flex-col gap-4 overflow-y-auto">
          <div className="rounded-2xl border border-border/70 bg-card">
            <div className="border-b border-border/70 px-4 py-3">
              <div className="text-sm font-semibold">Revision</div>
            </div>
            <div className="space-y-2 px-4 py-3 text-xs text-muted-foreground">
              <div>Revision ID: {selectedRevision?.id || "n/a"}</div>
              <div>Size: {selectedRevision?.byte_size ?? selectedEntry?.byte_size ?? 0}</div>
              <div>MIME: {selectedRevision?.mime_type || selectedEntry?.mime_type || "n/a"}</div>
            </div>
          </div>

          <div className="rounded-2xl border border-border/70 bg-card">
            <div className="border-b border-border/70 px-4 py-3">
              <div className="text-sm font-semibold">Workflow Links</div>
            </div>
            <div className="space-y-3 px-4 py-3">
              <div className="space-y-2">
                {links.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No linked workflows.</div>
                ) : (
                  links.map((link) => {
                    const agent = agents.find((item) => item.id === link.agent_id)
                    return (
                      <div key={link.agent_id} className="rounded-lg border border-border/70 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium">{agent?.name || link.agent_id}</div>
                            <div className="text-xs text-muted-foreground">{link.access_mode}</div>
                          </div>
                          <Button variant="ghost" size="icon" onClick={() => void handleDeleteLink(link.agent_id)}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              <div className="space-y-2 rounded-xl border border-dashed border-border/70 p-3">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Link2 className="h-4 w-4" />
                  Link Workflow
                </div>
                <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select workflow" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableAgents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={selectedAccessMode} onValueChange={(value) => setSelectedAccessMode(value as FileAccessMode)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="read">read</SelectItem>
                    <SelectItem value="read_write">read_write</SelectItem>
                  </SelectContent>
                </Select>
                <Button className="w-full" onClick={handleCreateLink} disabled={!selectedAgentId}>
                  Link
                </Button>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border/70 bg-card px-4 py-3 text-xs text-muted-foreground">
            <div className="font-medium text-foreground">Current space</div>
            <div className="mt-1 break-all">{spaceId}</div>
            <div className="mt-3">
              <Link href="/admin/files" className="text-primary hover:underline">
                Back to file spaces
              </Link>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
