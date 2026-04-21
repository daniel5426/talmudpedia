"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useOrganization } from "@/contexts/OrganizationContext"
import { useSidebar } from "@/components/ui/sidebar"
import { ArtifactEditorHeader } from "@/components/admin/artifacts/ArtifactEditorHeader"
import { ArtifactListView } from "@/components/admin/artifacts/ArtifactListView"
import {
  ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY,
  buildArtifactDetailHref,
  buildArtifactNewHref,
} from "@/components/admin/artifacts/artifactRoutes"
import { artifactsService, type Artifact, type ArtifactKind, type ArtifactLanguage } from "@/services/artifacts"

function artifactTransferFilename(displayName: string) {
  const base = displayName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return `${base || "artifact"}.artifact.json`
}

function downloadArtifactTransferFile(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export default function ArtifactsPage() {
  const { currentOrganization } = useOrganization()
  const { open: appSidebarOpen, openMobile: appSidebarOpenMobile, isMobile } = useSidebar()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const [bulkAction, setBulkAction] = useState<"duplicate" | "publish" | "delete" | "import" | "export" | null>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])

  const legacyMode = searchParams.get("mode")
  const legacyArtifactId = searchParams.get("id")
  const legacyKind = searchParams.get("kind") as ArtifactKind | null
  const legacyLanguage = searchParams.get("language") as ArtifactLanguage | null
  const legacyDraftKey = searchParams.get("draftKey")
  const shouldRedirectLegacyRoute = useMemo(
    () => legacyMode === "edit" || legacyMode === "create",
    [legacyMode],
  )

  const markNextEditorEntryShouldAutoCollapseSidebar = useCallback(() => {
    if (typeof window === "undefined") return
    const shouldAutoCollapse = isMobile ? appSidebarOpenMobile : appSidebarOpen
    if (!shouldAutoCollapse) return
    window.sessionStorage.setItem(ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY, "1")
  }, [appSidebarOpen, appSidebarOpenMobile, isMobile])

  const fetchArtifacts = useCallback(async () => {
    setLoading(true)
    try {
      const data = await artifactsService.list(currentOrganization?.id, { limit: 100, view: "summary" })
      setArtifacts(data.items)
    } catch (error) {
      console.error("Failed to fetch artifacts", error)
    } finally {
      setLoading(false)
    }
  }, [currentOrganization?.id])

  useEffect(() => {
    void fetchArtifacts()
  }, [fetchArtifacts])

  useEffect(() => {
    if (legacyMode === "edit" && legacyArtifactId) {
      router.replace(buildArtifactDetailHref(legacyArtifactId), { scroll: false })
      return
    }
    if (legacyMode === "create") {
      router.replace(buildArtifactNewHref({
        kind: legacyKind && ["agent_node", "rag_operator", "tool_impl"].includes(legacyKind) ? legacyKind : undefined,
        language: legacyLanguage === "javascript" ? "javascript" : legacyLanguage === "python" ? "python" : undefined,
        draftKey: legacyDraftKey || undefined,
      }), { scroll: false })
    }
  }, [legacyArtifactId, legacyDraftKey, legacyKind, legacyLanguage, legacyMode, router])

  const handleCreateArtifact = useCallback((kind: ArtifactKind, language: ArtifactLanguage) => {
    markNextEditorEntryShouldAutoCollapseSidebar()
    router.push(buildArtifactNewHref({ kind, language }))
  }, [markNextEditorEntryShouldAutoCollapseSidebar, router])

  const handleDuplicate = useCallback(async (artifact: Artifact) => {
    try {
      const duplicated = await artifactsService.duplicate(artifact.id, currentOrganization?.id)
      await fetchArtifacts()
      markNextEditorEntryShouldAutoCollapseSidebar()
      router.push(buildArtifactDetailHref(duplicated.id))
    } catch (error) {
      console.error("Failed to duplicate artifact", error)
      alert(error instanceof Error ? error.message : "Failed to duplicate artifact")
    }
  }, [currentOrganization?.id, fetchArtifacts, markNextEditorEntryShouldAutoCollapseSidebar, router])

  const handleDelete = useCallback(async (artifact: Artifact) => {
    if (!confirm(`Delete "${artifact.display_name}"?`)) return
    try {
      await artifactsService.delete(artifact.id, currentOrganization?.id)
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to delete artifact", error)
      alert("Failed to delete artifact")
    }
  }, [currentOrganization?.id, fetchArtifacts])

  const handlePublish = useCallback(async (artifact: Artifact) => {
    if (!confirm(`Publish "${artifact.display_name}"?`)) return
    setPublishingId(artifact.id)
    try {
      await artifactsService.publish(artifact.id, currentOrganization?.id)
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to publish artifact", error)
      alert(error instanceof Error ? error.message : "Publish failed")
    } finally {
      setPublishingId(null)
    }
  }, [currentOrganization?.id, fetchArtifacts])

  const handleBulkDuplicate = useCallback(async (selectedArtifacts: Artifact[]) => {
    if (selectedArtifacts.length === 0) return
    setBulkAction("duplicate")
    try {
      for (const artifact of selectedArtifacts) {
        await artifactsService.duplicate(artifact.id, currentOrganization?.id)
      }
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to duplicate selected artifacts", error)
      alert(error instanceof Error ? error.message : "Failed to duplicate selected artifacts")
    } finally {
      setBulkAction(null)
    }
  }, [currentOrganization?.id, fetchArtifacts])

  const handleBulkDelete = useCallback(async (selectedArtifacts: Artifact[]) => {
    if (selectedArtifacts.length === 0) return
    if (!confirm(`Delete ${selectedArtifacts.length} selected artifact${selectedArtifacts.length === 1 ? "" : "s"}?`)) return
    setBulkAction("delete")
    try {
      for (const artifact of selectedArtifacts) {
        await artifactsService.delete(artifact.id, currentOrganization?.id)
      }
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to delete selected artifacts", error)
      alert(error instanceof Error ? error.message : "Failed to delete selected artifacts")
    } finally {
      setBulkAction(null)
    }
  }, [currentOrganization?.id, fetchArtifacts])

  const handleBulkPublish = useCallback(async (selectedArtifacts: Artifact[]) => {
    if (selectedArtifacts.length === 0) return
    if (!confirm(`Publish ${selectedArtifacts.length} selected artifact${selectedArtifacts.length === 1 ? "" : "s"}?`)) return
    setBulkAction("publish")
    try {
      for (const artifact of selectedArtifacts) {
        await artifactsService.publish(artifact.id, currentOrganization?.id)
      }
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to publish selected artifacts", error)
      alert(error instanceof Error ? error.message : "Failed to publish selected artifacts")
    } finally {
      setBulkAction(null)
    }
  }, [currentOrganization?.id, fetchArtifacts])

  const handleDownloadArtifact = useCallback(async (artifact: Artifact) => {
    try {
      const transfer = await artifactsService.exportArtifact(artifact.id, currentOrganization?.id)
      downloadArtifactTransferFile(artifactTransferFilename(artifact.display_name), transfer)
    } catch (error) {
      console.error("Failed to export artifact", error)
      alert(error instanceof Error ? error.message : "Failed to export artifact")
    }
  }, [currentOrganization?.id])

  const handleBulkDownload = useCallback(async (selectedArtifacts: Artifact[]) => {
    if (selectedArtifacts.length === 0) return
    setBulkAction("export")
    try {
      for (const artifact of selectedArtifacts) {
        const transfer = await artifactsService.exportArtifact(artifact.id, currentOrganization?.id)
        downloadArtifactTransferFile(artifactTransferFilename(artifact.display_name), transfer)
      }
    } catch (error) {
      console.error("Failed to export selected artifacts", error)
      alert(error instanceof Error ? error.message : "Failed to export selected artifacts")
    } finally {
      setBulkAction(null)
    }
  }, [currentOrganization?.id])

  const handleUploadFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return
    setBulkAction("import")
    try {
      for (const file of files) {
        const text = await file.text()
        const payload = JSON.parse(text)
        await artifactsService.importArtifact(payload, currentOrganization?.id)
      }
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to import artifact files", error)
      alert(error instanceof Error ? error.message : "Failed to import artifact files")
    } finally {
      setBulkAction(null)
    }
  }, [currentOrganization?.id, fetchArtifacts])

  if (shouldRedirectLegacyRoute) {
    return (
      <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
        <ArtifactEditorHeader
          viewMode="list"
          displayName=""
          controlsDisabled
          sidebarOpen
          isAgentPanelOpen={false}
          isPublishing={false}
          isPublished={false}
          isSaving={false}
          disableSave={false}
          showDownload={false}
          showPublish={false}
          showVersions={false}
          versionsOpen={false}
          artifactVersions={[]}
          versionsLoading={false}
          applyingRevisionId={null}
          hasUnsavedChanges={false}
          onRefreshArtifacts={() => {}}
          onCreateArtifact={() => {}}
          onToggleSidebar={() => {}}
          onToggleAgentPanel={() => {}}
          onStartNewChat={() => {}}
          onOpenChatHistory={() => {}}
          onVersionsOpenChange={() => {}}
          onSelectVersion={() => {}}
          onPublish={() => {}}
          onDownload={() => {}}
          onRunTest={() => {}}
          onSave={() => {}}
        />
        <div className="flex-1 overflow-auto px-4 pb-4 pt-3" data-admin-page-scroll>
          <ArtifactListView
            loading
            artifacts={[]}
            publishingId={null}
            bulkAction={null}
            onEditArtifact={() => {}}
            onDuplicateArtifact={() => {}}
            onDeleteArtifact={() => {}}
            onPublishArtifact={() => {}}
            onBulkDuplicateArtifacts={() => Promise.resolve()}
            onBulkDeleteArtifacts={() => Promise.resolve()}
            onBulkPublishArtifacts={() => Promise.resolve()}
            onDownloadArtifact={() => Promise.resolve()}
            onUploadArtifactFiles={() => Promise.resolve()}
            onBulkDownloadArtifacts={() => Promise.resolve()}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <ArtifactEditorHeader
        viewMode="list"
        displayName=""
        controlsDisabled={loading}
        sidebarOpen
        isAgentPanelOpen={false}
        isPublishing={false}
        isPublished={false}
        isSaving={false}
        disableSave={false}
        showDownload={false}
        showPublish={false}
        showVersions={false}
        versionsOpen={false}
        artifactVersions={[]}
        versionsLoading={false}
        applyingRevisionId={null}
        hasUnsavedChanges={false}
        onRefreshArtifacts={() => {
          void fetchArtifacts()
        }}
        onCreateArtifact={handleCreateArtifact}
        onToggleSidebar={() => {}}
        onToggleAgentPanel={() => {}}
        onStartNewChat={() => {}}
        onOpenChatHistory={() => {}}
        onVersionsOpenChange={() => {}}
        onSelectVersion={() => {}}
        onPublish={() => {}}
        onDownload={() => {}}
        onRunTest={() => {}}
        onSave={() => {}}
      />
      <div className="flex-1 overflow-auto px-4 pb-4 pt-3" data-admin-page-scroll>
        <ArtifactListView
          loading={loading}
          artifacts={artifacts}
          publishingId={publishingId}
          bulkAction={bulkAction}
          onEditArtifact={(artifact) => {
            markNextEditorEntryShouldAutoCollapseSidebar()
            router.push(buildArtifactDetailHref(artifact.id))
          }}
          onDuplicateArtifact={(artifact) => {
            void handleDuplicate(artifact)
          }}
          onDeleteArtifact={(artifact) => {
            void handleDelete(artifact)
          }}
          onPublishArtifact={(artifact) => {
            void handlePublish(artifact)
          }}
          onBulkDuplicateArtifacts={(selectedArtifacts) => handleBulkDuplicate(selectedArtifacts)}
          onBulkDeleteArtifacts={(selectedArtifacts) => handleBulkDelete(selectedArtifacts)}
          onBulkPublishArtifacts={(selectedArtifacts) => handleBulkPublish(selectedArtifacts)}
          onDownloadArtifact={(artifact) => handleDownloadArtifact(artifact)}
          onUploadArtifactFiles={(files) => handleUploadFiles(files)}
          onBulkDownloadArtifacts={(selectedArtifacts) => handleBulkDownload(selectedArtifacts)}
        />
      </div>
    </div>
  )
}
