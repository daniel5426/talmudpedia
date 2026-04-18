"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import dynamic from "next/dynamic"
import { useParams, useRouter } from "next/navigation"

import { FileSpaceEditorHeader } from "@/components/admin/files/FileSpaceEditorHeader"
import { FileSpaceConfigPanel } from "@/components/admin/files/FileSpaceConfigPanel"
import { FileSpaceWorkspaceEditor } from "@/components/admin/files/FileSpaceWorkspaceEditor"
import { ARTIFACT_CONFIG_FILE_PATH } from "@/components/admin/artifacts/artifactWorkspaceUtils"
import { Textarea } from "@/components/ui/textarea"
import {
  agentService,
  fileSpacesService,
  type Agent,
  type FileAccessMode,
  type FileEntryRevision,
  type FileSpace,
  type FileSpaceEntry,
} from "@/services"

const FileSpacePreviewPane = dynamic(
  () => import("@/components/admin/files/FileSpacePreviewPane").then((mod) => mod.FileSpacePreviewPane),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <p className="text-sm text-muted-foreground/50">Loading preview...</p>
      </div>
    ),
  },
)

type TextDraftState = {
  content: string
  savedContent: string
  mimeType: string | null
  revision: FileEntryRevision | null
}

function isPathOrDescendant(path: string, rootPath: string) {
  return path === rootPath || path.startsWith(`${rootPath}/`)
}

function remapPath(path: string, sourcePath: string, targetPath: string) {
  if (path === sourcePath) return targetPath
  if (!path.startsWith(`${sourcePath}/`)) return path
  return `${targetPath}/${path.slice(sourcePath.length + 1)}`
}

function remapOpenTabs(openTabs: string[], sourcePath: string, targetPath: string) {
  const seen = new Set<string>()
  const nextTabs: string[] = []
  for (const path of openTabs) {
    const nextPath = path === ARTIFACT_CONFIG_FILE_PATH ? path : remapPath(path, sourcePath, targetPath)
    if (seen.has(nextPath)) continue
    seen.add(nextPath)
    nextTabs.push(nextPath)
  }
  return nextTabs
}

function pruneTextDrafts(textDrafts: Record<string, TextDraftState>, entries: FileSpaceEntry[]) {
  const textPaths = new Set(
    entries.filter((entry) => entry.entry_type === "file" && entry.is_text).map((entry) => entry.path),
  )
  return Object.fromEntries(
    Object.entries(textDrafts).filter(([path]) => textPaths.has(path)),
  ) as Record<string, TextDraftState>
}

export default function FileSpaceDetailPage() {
  const params = useParams()
  const router = useRouter()
  const uploadRef = useRef<HTMLInputElement | null>(null)
  const spaceId = String(params?.spaceId || "")

  const [space, setSpace] = useState<FileSpace | null>(null)
  const [entries, setEntries] = useState<FileSpaceEntry[]>([])
  const [links, setLinks] = useState<{ agent_id: string; access_mode: FileAccessMode }[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeFilePath, setActiveFilePath] = useState<string>(ARTIFACT_CONFIG_FILE_PATH)
  const [openTabs, setOpenTabs] = useState<string[]>([ARTIFACT_CONFIG_FILE_PATH])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [saving, setSaving] = useState(false)
  const [textDrafts, setTextDrafts] = useState<Record<string, TextDraftState>>({})

  const activeFilePathRef = useRef(activeFilePath)
  const entriesRef = useRef(entries)
  const textDraftsRef = useRef(textDrafts)
  const loadAllRef = useRef<((nextSelectedPath?: string | null, forceReloadActiveText?: boolean) => Promise<void>) | null>(
    null,
  )
  const saveAllRef = useRef<(() => Promise<void>) | null>(null)

  useEffect(() => {
    activeFilePathRef.current = activeFilePath
  }, [activeFilePath])

  useEffect(() => {
    entriesRef.current = entries
  }, [entries])

  useEffect(() => {
    textDraftsRef.current = textDrafts
  }, [textDrafts])

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.path === activeFilePath) || null,
    [entries, activeFilePath],
  )

  const selectedTextDraft =
    selectedEntry?.entry_type === "file" && selectedEntry.is_text ? textDrafts[selectedEntry.path] || null : null

  const unsavedPaths = useMemo(
    () =>
      Object.entries(textDrafts)
        .filter(([, draft]) => draft.content !== draft.savedContent)
        .map(([path]) => path),
    [textDrafts],
  )
  const hasUnsavedChanges = unsavedPaths.length > 0

  async function loadTextDraft(path: string, entryOverride?: FileSpaceEntry | null, forceReload = false) {
    const entry = entryOverride || entriesRef.current.find((item) => item.path === path) || null
    if (!entry || entry.entry_type !== "file" || !entry.is_text) return

    const existing = textDraftsRef.current[path]
    if (existing && existing.content !== existing.savedContent) return
    if (existing && !forceReload) return

    const payload = await fileSpacesService.readText(spaceId, path)
    setTextDrafts((current) => {
      const draft = current[path]
      if (draft && draft.content !== draft.savedContent) return current
      return {
        ...current,
        [path]: {
          content: payload.content,
          savedContent: payload.content,
          mimeType: payload.entry.mime_type,
          revision: payload.revision,
        },
      }
    })
  }

  async function loadAll(nextSelectedPath?: string | null, forceReloadActiveText = false) {
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
      setTextDrafts((current) => pruneTextDrafts(current, treePayload.items))

      const requestedPath = nextSelectedPath !== undefined ? nextSelectedPath : activeFilePathRef.current
      const nextEntry = treePayload.items.find((item) => item.path === requestedPath) || null
      const resolvedPath =
        requestedPath === ARTIFACT_CONFIG_FILE_PATH
          ? ARTIFACT_CONFIG_FILE_PATH
          : nextEntry?.path || ARTIFACT_CONFIG_FILE_PATH

      setActiveFilePath(resolvedPath)
      if (nextEntry?.entry_type === "file" && nextEntry.is_text) {
        await loadTextDraft(nextEntry.path, nextEntry, forceReloadActiveText)
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
      void loadAllRef.current?.()
    }
  }, [spaceId])

  async function handleActiveFileChange(path: string) {
    if (path === activeFilePathRef.current) return
    setActiveFilePath(path)
    if (path === ARTIFACT_CONFIG_FILE_PATH) return
    const entry = entriesRef.current.find((item) => item.path === path) || null
    if (entry?.entry_type === "file" && entry.is_text) {
      try {
        await loadTextDraft(path, entry)
      } catch (err) {
        console.error(err)
        setError("Failed to load file.")
      }
    }
  }

  async function handleSaveAll() {
    const dirtyPaths = Object.entries(textDraftsRef.current)
      .filter(([, draft]) => draft.content !== draft.savedContent)
      .map(([path]) => path)

    if (dirtyPaths.length === 0) return

    try {
      setSaving(true)
      setError(null)
      for (const path of dirtyPaths) {
        const draft = textDraftsRef.current[path]
        const entry = entriesRef.current.find((item) => item.path === path) || null
        if (!draft || !entry || entry.entry_type !== "file") continue

        const payload = await fileSpacesService.writeText(spaceId, {
          path,
          content: draft.content,
          mime_type: entry.mime_type ?? draft.mimeType,
        })

        setTextDrafts((current) => {
          const nextDraft = current[path]
          if (!nextDraft) return current
          return {
            ...current,
            [path]: {
              content: nextDraft.content,
              savedContent: nextDraft.content,
              mimeType: payload.entry.mime_type,
              revision: payload.revision,
            },
          }
        })
      }
      await loadAll(activeFilePathRef.current)
    } catch (err) {
      console.error(err)
      setError("Failed to save files.")
    } finally {
      setSaving(false)
    }
  }
  loadAllRef.current = loadAll
  saveAllRef.current = handleSaveAll

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return
      if (event.key.toLowerCase() !== "s") return
      event.preventDefault()
      if (!hasUnsavedChanges || saving) return
      void saveAllRef.current?.()
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [hasUnsavedChanges, saving])

  function getDefaultBasePath() {
    if (activeFilePath === ARTIFACT_CONFIG_FILE_PATH || !activeFilePath) return ""
    const entry = entries.find((item) => item.path === activeFilePath)
    if (entry?.entry_type === "directory") return activeFilePath
    const parts = activeFilePath.split("/")
    parts.pop()
    return parts.join("/")
  }

  async function handleCreateFolder() {
    const base = getDefaultBasePath()
    const defaultVal = base ? `${base}/NewFolder` : "NewFolder"
    const path = window.prompt("Directory path", defaultVal)
    if (!path) return
    try {
      await fileSpacesService.mkdir(spaceId, path)
      await loadAll()
    } catch (err) {
      console.error(err)
      setError("Failed to create directory.")
    }
  }

  async function handleDeleteEntry(path: string) {
    if (!window.confirm(`Delete ${path}?`)) return
    try {
      await fileSpacesService.deleteEntry(spaceId, path)
      const nextActivePath = isPathOrDescendant(activeFilePathRef.current, path)
        ? ARTIFACT_CONFIG_FILE_PATH
        : activeFilePathRef.current

      setTextDrafts((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([draftPath]) => !isPathOrDescendant(draftPath, path)),
        ) as Record<string, TextDraftState>,
      )
      setOpenTabs((current) => {
        const nextTabs = current.filter((tabPath) => !isPathOrDescendant(tabPath, path))
        return nextTabs.length > 0 ? nextTabs : [ARTIFACT_CONFIG_FILE_PATH]
      })
      setActiveFilePath(nextActivePath)
      await loadAll(nextActivePath)
    } catch (err) {
      console.error(err)
      setError("Failed to delete entry.")
    }
  }

  async function handleMoveEntry(sourcePath: string, targetPath: string) {
    try {
      setLoading(true)
      await fileSpacesService.move(spaceId, { from_path: sourcePath, to_path: targetPath })

      const nextActivePath = isPathOrDescendant(activeFilePathRef.current, sourcePath)
        ? remapPath(activeFilePathRef.current, sourcePath, targetPath)
        : activeFilePathRef.current

      setTextDrafts((current) => {
        const nextDrafts: Record<string, TextDraftState> = {}
        for (const [path, draft] of Object.entries(current)) {
          nextDrafts[remapPath(path, sourcePath, targetPath)] = draft
        }
        return nextDrafts
      })
      setOpenTabs((current) => remapOpenTabs(current, sourcePath, targetPath))
      setActiveFilePath(nextActivePath)
      await loadAll(nextActivePath)
    } catch (err) {
      console.error(err)
      setError("Failed to move entry.")
      setLoading(false)
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return
    const base = getDefaultBasePath()
    const defaultVal = base ? `${base}/${file.name}` : file.name
    const path = window.prompt("Upload path (including filename)", defaultVal)
    if (!path) return
    try {
      await fileSpacesService.uploadBlob(spaceId, { path, file })
      setOpenTabs((current) => (current.includes(path) ? current : [...current, path]))
      await loadAll(path)
    } catch (err) {
      console.error(err)
      setError("Failed to upload file.")
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

  async function handleCreateLink(agentId: string, mode: FileAccessMode) {
    try {
      await fileSpacesService.upsertLink(spaceId, { agent_id: agentId, access_mode: mode })
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

  const hiddenUploadInput = (
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
  )

  function handleDownloadEntry(path: string) {
    const url = fileSpacesService.buildDownloadUrl(spaceId, path)
    window.open(url, "_blank", "noopener,noreferrer")
  }

  const renderEditorContent = () => {
    if (!selectedEntry) {
      return (
        <div className="flex h-full flex-col items-center justify-center text-center">
          <p className="text-sm text-muted-foreground/50">File not found.</p>
        </div>
      )
    }

    if (selectedEntry.entry_type === "directory") {
      return (
        <div className="flex h-full flex-col items-center justify-center text-center">
          <p className="text-sm text-muted-foreground/50">This is a directory.</p>
        </div>
      )
    }

    return (
      <div className="relative flex h-full w-full flex-col">
        <div className="relative flex-1 min-h-0">
          {selectedEntry.is_text ? (
            <Textarea
              value={selectedTextDraft?.content ?? ""}
              onChange={(event) =>
                setTextDrafts((current) => ({
                  ...current,
                  [selectedEntry.path]: {
                    content: event.target.value,
                    savedContent: current[selectedEntry.path]?.savedContent ?? "",
                    mimeType: current[selectedEntry.path]?.mimeType ?? selectedEntry.mime_type,
                    revision: current[selectedEntry.path]?.revision ?? null,
                  },
                }))
              }
              className="absolute inset-0 h-full w-full resize-none rounded-none border-0 bg-transparent px-5 py-4 font-mono text-sm leading-relaxed focus-visible:ring-0 focus-visible:ring-offset-0"
              spellCheck={false}
            />
          ) : (
            <FileSpacePreviewPane spaceId={spaceId} entry={selectedEntry} />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      {hiddenUploadInput}
      <FileSpaceEditorHeader
        viewMode="detail"
        spaceName={space?.name}
        spaceId={spaceId}
        controlsDisabled={loading}
        hasUnsavedChanges={hasUnsavedChanges}
        isSaving={saving}
        onRefresh={() => loadAll(undefined, true)}
        onSaveAll={() => {
          void handleSaveAll()
        }}
        onArchiveSpace={handleArchiveSpace}
      />
      {error && (
        <div className="pointer-events-none fixed bottom-4 right-4 z-50 w-full max-w-md px-4 sm:px-0">
          <div className="pointer-events-auto rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive shadow-lg">
            {error}
          </div>
        </div>
      )}
      <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
        <div className="relative flex min-h-0 w-full flex-1 overflow-hidden">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <FileSpaceWorkspaceEditor
                entries={entries}
                loading={loading}
                activeFilePath={activeFilePath}
                unsavedPaths={unsavedPaths}
                onActiveFileChange={handleActiveFileChange}
                onAddFolder={handleCreateFolder}
                onUploadFile={() => uploadRef.current?.click()}
                onDeleteEntry={handleDeleteEntry}
                onDownloadEntry={handleDownloadEntry}
                onMoveEntry={handleMoveEntry}
                sidebarOpen={sidebarOpen}
                onSidebarOpenChange={setSidebarOpen}
                openTabs={openTabs}
                setOpenTabs={setOpenTabs}
                configContent={
                  <FileSpaceConfigPanel
                    space={space}
                    links={links}
                    agents={agents}
                    onLinkAgent={handleCreateLink}
                    onUnlinkAgent={handleDeleteLink}
                  />
                }
                editorContent={renderEditorContent()}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
