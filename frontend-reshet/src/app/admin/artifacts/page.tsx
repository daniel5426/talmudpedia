"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useTenant } from "@/contexts/TenantContext"
import { useSidebar } from "@/components/ui/sidebar"
import { ArtifactEditorHeader } from "@/components/admin/artifacts/ArtifactEditorHeader"
import { ArtifactListView } from "@/components/admin/artifacts/ArtifactListView"
import {
  ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY,
  buildArtifactDetailHref,
  buildArtifactNewHref,
} from "@/components/admin/artifacts/artifactRoutes"
import { artifactsService, type Artifact, type ArtifactKind, type ArtifactLanguage } from "@/services/artifacts"

export default function ArtifactsPage() {
  const { currentTenant } = useTenant()
  const { open: appSidebarOpen, openMobile: appSidebarOpenMobile, isMobile } = useSidebar()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [publishingId, setPublishingId] = useState<string | null>(null)
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
      const data = await artifactsService.list(currentTenant?.slug)
      setArtifacts(data)
    } catch (error) {
      console.error("Failed to fetch artifacts", error)
    } finally {
      setLoading(false)
    }
  }, [currentTenant?.slug])

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
      const duplicated = await artifactsService.duplicate(artifact.id, currentTenant?.slug)
      await fetchArtifacts()
      markNextEditorEntryShouldAutoCollapseSidebar()
      router.push(buildArtifactDetailHref(duplicated.id))
    } catch (error) {
      console.error("Failed to duplicate artifact", error)
      alert(error instanceof Error ? error.message : "Failed to duplicate artifact")
    }
  }, [currentTenant?.slug, fetchArtifacts, markNextEditorEntryShouldAutoCollapseSidebar, router])

  const handleDelete = useCallback(async (artifact: Artifact) => {
    if (!confirm(`Delete "${artifact.display_name}"?`)) return
    try {
      await artifactsService.delete(artifact.id, currentTenant?.slug)
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to delete artifact", error)
      alert("Failed to delete artifact")
    }
  }, [currentTenant?.slug, fetchArtifacts])

  const handlePublish = useCallback(async (artifact: Artifact) => {
    if (!confirm(`Publish "${artifact.display_name}"?`)) return
    setPublishingId(artifact.id)
    try {
      await artifactsService.publish(artifact.id, currentTenant?.slug)
      await fetchArtifacts()
    } catch (error) {
      console.error("Failed to publish artifact", error)
      alert(error instanceof Error ? error.message : "Publish failed")
    } finally {
      setPublishingId(null)
    }
  }, [currentTenant?.slug, fetchArtifacts])

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
          onVersionsOpenChange={() => {}}
          onSelectVersion={() => {}}
          onPublish={() => {}}
          onRunTest={() => {}}
          onSave={() => {}}
        />
        <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
          <div className="h-full overflow-auto" data-admin-page-scroll>
            <ArtifactListView
              loading
              artifacts={[]}
              publishingId={null}
              onEditArtifact={() => {}}
              onDuplicateArtifact={() => {}}
              onDeleteArtifact={() => {}}
              onPublishArtifact={() => {}}
            />
          </div>
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
        onVersionsOpenChange={() => {}}
        onSelectVersion={() => {}}
        onPublish={() => {}}
        onRunTest={() => {}}
        onSave={() => {}}
      />
      <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
        <div className="h-full overflow-auto" data-admin-page-scroll>
          <ArtifactListView
            loading={loading}
            artifacts={artifacts}
            publishingId={publishingId}
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
          />
        </div>
      </div>
    </div>
  )
}
