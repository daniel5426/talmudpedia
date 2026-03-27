"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useTenant } from "@/contexts/TenantContext"
import { Skeleton } from "@/components/ui/skeleton"
import { ArtifactEditorHeader } from "@/components/admin/artifacts/ArtifactEditorHeader"
import { ArtifactListView } from "@/components/admin/artifacts/ArtifactListView"
import { buildArtifactDetailHref, buildArtifactNewHref } from "@/components/admin/artifacts/artifactRoutes"
import { artifactsService, type Artifact, type ArtifactKind, type ArtifactLanguage } from "@/services/artifacts"

function ArtifactListSkeleton() {
  return (
    <div className="h-full overflow-auto" data-admin-page-scroll>
      <div className="space-y-6 p-6">
        <div className="rounded-xl border bg-card p-5">
          <div className="flex items-center justify-between gap-4 border-b pb-4">
            <div className="space-y-2">
              <Skeleton className="h-6 w-44" />
              <Skeleton className="h-4 w-72" />
            </div>
            <Skeleton className="h-9 w-44 rounded-md" />
          </div>
          <div className="space-y-2 pt-4">
            <div className="grid grid-cols-[minmax(0,2.2fr)_140px_140px_90px_60px] gap-4 px-4 py-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-4 w-10" />
              <Skeleton className="h-4 w-8" />
            </div>
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} className="grid grid-cols-[minmax(0,2.2fr)_140px_140px_90px_60px] items-center gap-4 rounded-lg border px-4 py-4">
                <div className="space-y-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-24" />
                </div>
                <Skeleton className="h-6 w-20 rounded-full" />
                <Skeleton className="h-6 w-20 rounded-full" />
                <Skeleton className="h-4 w-12" />
                <Skeleton className="ml-auto h-8 w-8 rounded-md" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ArtifactsPage() {
  const { currentTenant } = useTenant()
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
    router.push(buildArtifactNewHref({ kind, language }))
  }, [router])

  const handleDuplicate = useCallback(async (artifact: Artifact) => {
    try {
      const duplicated = await artifactsService.duplicate(artifact.id, currentTenant?.slug)
      await fetchArtifacts()
      router.push(buildArtifactDetailHref(duplicated.id))
    } catch (error) {
      console.error("Failed to duplicate artifact", error)
      alert(error instanceof Error ? error.message : "Failed to duplicate artifact")
    }
  }, [currentTenant?.slug, fetchArtifacts, router])

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
          <ArtifactListSkeleton />
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
        {loading ? (
          <ArtifactListSkeleton />
        ) : (
          <div className="h-full overflow-auto" data-admin-page-scroll>
            <ArtifactListView
              artifacts={artifacts}
              publishingId={publishingId}
              onEditArtifact={(artifact) => router.push(buildArtifactDetailHref(artifact.id))}
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
        )}
      </div>
    </div>
  )
}
