"use client"

import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2 } from "lucide-react"

import { useTenant } from "@/contexts/TenantContext"
import { useSidebar } from "@/components/ui/sidebar"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { fillPromptMentionJsonToken } from "@/components/shared/PromptMentionJsonEditor"
import { PromptModal } from "@/components/shared/PromptModal"
import { usePromptMentionModal } from "@/components/shared/usePromptMentionModal"
import { ArtifactConfigPanel } from "@/components/admin/artifacts/ArtifactConfigPanel"
import { ArtifactEditorHeader } from "@/components/admin/artifacts/ArtifactEditorHeader"
import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"
import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"
import { ArtifactCodingChatPanel } from "@/features/artifact-coding/ArtifactCodingChatPanel"
import { useArtifactCodingChat } from "@/features/artifact-coding/useArtifactCodingChat"
import { credentialsService, type IntegrationCredential } from "@/services"
import {
  artifactsService,
  type AgentArtifactContract,
  type Artifact,
  type ArtifactCapabilityConfig,
  type ArtifactKind,
  type ArtifactLanguage,
  type ArtifactVersionListItem,
  type RAGArtifactContract,
} from "@/services/artifacts"
import { type ArtifactFormData, createFormDataForKind } from "@/components/admin/artifacts/artifactEditorState"
import {
  buildArtifactPayload,
  buildArtifactUpdatePayload,
  buildConvertPayload,
  formDataFromArtifact,
  formDataFromArtifactVersion,
  formDataFromDraftSnapshot,
  getArtifactLanguageWarningPaths,
  kindLabel,
  parseToolContract,
  serializeArtifactFormData,
  tryParseObject,
} from "@/components/admin/artifacts/artifactPageUtils"
import {
  ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY,
  buildArtifactDetailHref,
  buildArtifactNewHref,
} from "@/components/admin/artifacts/artifactRoutes"

type ArtifactEditorScreenProps = {
  mode: "create" | "edit"
  artifactId?: string
  initialKind?: ArtifactKind
  initialLanguage?: ArtifactLanguage
  initialDraftKey?: string
}

function getDefaultActiveFilePath(formData: ArtifactFormData): string {
  return formData.entry_module_path || formData.source_files[0]?.path || "__CONFIG__"
}

function createArtifactChatDraftKey(): string {
  return crypto.randomUUID()
}

export function ArtifactEditorScreen({
  mode,
  artifactId,
  initialKind = "agent_node",
  initialLanguage = "python",
  initialDraftKey,
}: ArtifactEditorScreenProps) {
  const { currentTenant } = useTenant()
  const { setOpen: setAppSidebarOpen, setOpenMobile: setAppSidebarOpenMobile, isMobile } = useSidebar()
  const router = useRouter()

  const [loading, setLoading] = useState(mode === "edit")
  const [saving, setSaving] = useState(false)
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const [converting, setConverting] = useState(false)
  const [availableCredentials, setAvailableCredentials] = useState<IntegrationCredential[]>([])
  const initialEditorFormData = useMemo(() => createFormDataForKind(initialKind, initialLanguage), [initialKind, initialLanguage])
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
  const [formData, setFormData] = useState<ArtifactFormData>(initialEditorFormData)
  const [convertTargetKind, setConvertTargetKind] = useState<ArtifactKind>(initialKind === "agent_node" ? "rag_operator" : "agent_node")
  const [activeFilePath, setActiveFilePath] = useState(() => getDefaultActiveFilePath(initialEditorFormData))
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [artifactChatDraftKey, setArtifactChatDraftKey] = useState(initialDraftKey || "")
  const [chatError, setChatError] = useState<string | null>(null)
  const [isChatHistoryOpen, setIsChatHistoryOpen] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [artifactVersions, setArtifactVersions] = useState<ArtifactVersionListItem[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [applyingRevisionId, setApplyingRevisionId] = useState<string | null>(null)
  const [publishWarningOpen, setPublishWarningOpen] = useState(false)
  const promptMentionModal = usePromptMentionModal<{ tokenRange: { from: number; to: number } }>()
  const lastWorkingDraftSignatureRef = useRef<string | null>(null)
  const workingDraftSaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const viewMode = mode

  const collapseAppSidebarOnEnter = useEffectEvent(() => {
    if (typeof window === "undefined") return
    const shouldAutoCollapse = window.sessionStorage.getItem(ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY) === "1"
    window.sessionStorage.removeItem(ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY)
    if (!shouldAutoCollapse) return
    if (isMobile) {
      setAppSidebarOpenMobile(false)
      return
    }
    setAppSidebarOpen(false)
  })

  const syncSelectedArtifact = useCallback((artifact: Artifact) => {
    setSelectedArtifact(artifact)
    setConvertTargetKind(artifact.kind === "agent_node" ? "rag_operator" : "agent_node")
  }, [])

  const loadArtifactEditorState = useCallback(async (nextArtifactId: string) => {
    const fullArtifact = await artifactsService.get(nextArtifactId, currentTenant?.slug)
    let nextFormData = formDataFromArtifact(fullArtifact)
    try {
      const workingDraft = await artifactsService.getWorkingDraft(nextArtifactId, currentTenant?.slug)
      if (workingDraft?.draft_snapshot && Object.keys(workingDraft.draft_snapshot).length > 0) {
        nextFormData = formDataFromDraftSnapshot(fullArtifact, workingDraft.draft_snapshot)
      }
    } catch (error) {
      console.error("Failed to load artifact working draft", error)
    }
    syncSelectedArtifact(fullArtifact)
    setFormData(nextFormData)
    setActiveFilePath(getDefaultActiveFilePath(nextFormData))
    lastWorkingDraftSignatureRef.current = serializeArtifactFormData(nextFormData)
    return fullArtifact
  }, [currentTenant?.slug, syncSelectedArtifact])

  const fetchAvailableCredentials = useCallback(async () => {
    try {
      const items = await credentialsService.listCredentials()
      setAvailableCredentials(items)
    } catch (error) {
      console.error("Failed to fetch integration credentials", error)
    }
  }, [])

  useEffect(() => {
    void fetchAvailableCredentials()
  }, [fetchAvailableCredentials])

  useEffect(() => {
    collapseAppSidebarOnEnter()
  }, [collapseAppSidebarOnEnter])

  useEffect(() => {
    if (mode !== "edit" || !artifactId) return
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        await loadArtifactEditorState(artifactId)
      } catch (error) {
        console.error("Failed to load artifact editor state", error)
        if (!cancelled) {
          alert(error instanceof Error ? error.message : "Failed to load artifact")
          router.replace("/admin/artifacts")
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [artifactId, loadArtifactEditorState, mode, router])

  useEffect(() => {
    if (mode !== "create") return
    const draftKey = initialDraftKey?.trim() || createArtifactChatDraftKey()
    const nextFormData = createFormDataForKind(initialKind, initialLanguage)
    setFormData(nextFormData)
    setSelectedArtifact(null)
    setActiveFilePath(getDefaultActiveFilePath(nextFormData))
    setConvertTargetKind(initialKind === "agent_node" ? "rag_operator" : "agent_node")
    setArtifactChatDraftKey(draftKey)
    lastWorkingDraftSignatureRef.current = serializeArtifactFormData(nextFormData)
    if (!initialDraftKey?.trim()) {
      router.replace(buildArtifactNewHref({ kind: initialKind, language: initialLanguage, draftKey }), { scroll: false })
    }
    setLoading(false)
  }, [initialDraftKey, initialKind, initialLanguage, mode, router])

  const savedFormSignature = useMemo(() => {
    if (!selectedArtifact) return null
    return serializeArtifactFormData(formDataFromArtifact(selectedArtifact))
  }, [selectedArtifact])
  const currentFormSignature = useMemo(() => serializeArtifactFormData(formData), [formData])
  const hasUnsavedChanges = savedFormSignature !== null && currentFormSignature !== savedFormSignature
  const workingDraftSnapshot = useMemo(() => ({
    ...formData,
    source_files: formData.source_files.map((file) => ({ ...file })),
  }), [formData])

  const loadArtifactVersions = useCallback(async () => {
    if (!selectedArtifact?.id) return
    setLoadingVersions(true)
    try {
      const versions = await artifactsService.listVersions(selectedArtifact.id, currentTenant?.slug)
      setArtifactVersions(versions)
    } catch (error) {
      console.error("Failed to load artifact versions", error)
      alert(error instanceof Error ? error.message : "Failed to load artifact versions")
    } finally {
      setLoadingVersions(false)
    }
  }, [currentTenant?.slug, selectedArtifact?.id])

  useEffect(() => {
    if (!versionsOpen || !selectedArtifact?.id) return
    void loadArtifactVersions()
  }, [loadArtifactVersions, selectedArtifact?.id, versionsOpen])

  const applyArtifactVersion = useCallback(async (revisionId: string) => {
    if (!selectedArtifact?.id) return
    setApplyingRevisionId(revisionId)
    try {
      const version = await artifactsService.getVersion(selectedArtifact.id, revisionId, currentTenant?.slug)
      const nextFormData = formDataFromArtifactVersion(version)
      setFormData(nextFormData)
      setActiveFilePath(getDefaultActiveFilePath(nextFormData))
      setVersionsOpen(false)
    } catch (error) {
      console.error("Failed to load artifact version", error)
      alert(error instanceof Error ? error.message : "Failed to load artifact version")
    } finally {
      setApplyingRevisionId(null)
    }
  }, [currentTenant?.slug, selectedArtifact?.id])

  const persistWorkingDraft = useCallback(async (nextArtifactId: string, snapshot = workingDraftSnapshot, signature = currentFormSignature) => {
    if (workingDraftSaveTimeoutRef.current) {
      clearTimeout(workingDraftSaveTimeoutRef.current)
      workingDraftSaveTimeoutRef.current = null
    }
    await artifactsService.updateWorkingDraft(
      nextArtifactId,
      {
        artifact_id: nextArtifactId,
        draft_snapshot: snapshot,
      },
      currentTenant?.slug,
    )
    lastWorkingDraftSignatureRef.current = signature
  }, [currentFormSignature, currentTenant?.slug, workingDraftSnapshot])

  useEffect(() => {
    if (workingDraftSaveTimeoutRef.current) {
      clearTimeout(workingDraftSaveTimeoutRef.current)
      workingDraftSaveTimeoutRef.current = null
    }
    if (mode !== "edit" || !selectedArtifact?.id) {
      return
    }
    if (currentFormSignature === lastWorkingDraftSignatureRef.current) {
      return
    }
    workingDraftSaveTimeoutRef.current = setTimeout(() => {
      void persistWorkingDraft(selectedArtifact.id).catch((error) => {
        console.error("Failed to persist artifact working draft", error)
      })
    }, 500)
    return () => {
      if (workingDraftSaveTimeoutRef.current) {
        clearTimeout(workingDraftSaveTimeoutRef.current)
        workingDraftSaveTimeoutRef.current = null
      }
    }
  }, [currentFormSignature, mode, persistWorkingDraft, selectedArtifact?.id])

  const updateFormData = useCallback((field: keyof ArtifactFormData, value: string | ArtifactKind | ArtifactLanguage | ArtifactFormData["source_files"]) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }, [])

  const applyDraftSnapshot = useCallback((snapshot: Record<string, unknown>) => {
    setFormData((prev) => ({
      display_name: typeof snapshot.display_name === "string" ? snapshot.display_name : prev.display_name,
      description: typeof snapshot.description === "string" ? snapshot.description : prev.description,
      kind: (typeof snapshot.kind === "string" ? snapshot.kind : prev.kind) as ArtifactKind,
      language: (typeof snapshot.language === "string" ? snapshot.language : prev.language) as ArtifactLanguage,
      source_files: Array.isArray(snapshot.source_files) ? snapshot.source_files as ArtifactFormData["source_files"] : prev.source_files,
      entry_module_path: typeof snapshot.entry_module_path === "string" ? snapshot.entry_module_path : prev.entry_module_path,
      dependencies: typeof snapshot.dependencies === "string"
        ? snapshot.dependencies
        : (typeof snapshot.python_dependencies === "string" ? snapshot.python_dependencies : prev.dependencies),
      runtime_target: typeof snapshot.runtime_target === "string" ? snapshot.runtime_target : prev.runtime_target,
      capabilities: typeof snapshot.capabilities === "string" ? snapshot.capabilities : prev.capabilities,
      config_schema: typeof snapshot.config_schema === "string" ? snapshot.config_schema : prev.config_schema,
      agent_contract: typeof snapshot.agent_contract === "string" ? snapshot.agent_contract : prev.agent_contract,
      rag_contract: typeof snapshot.rag_contract === "string" ? snapshot.rag_contract : prev.rag_contract,
      tool_contract: typeof snapshot.tool_contract === "string" ? snapshot.tool_contract : prev.tool_contract,
    }))
  }, [])

  useEffect(() => {
    if (activeFilePath === "__CONFIG__") return
    if (formData.source_files.some((file) => file.path === activeFilePath)) return
    setActiveFilePath(getDefaultActiveFilePath(formData))
  }, [activeFilePath, formData])

  const handleSave = async (): Promise<Artifact | null> => {
    if (!formData.display_name.trim()) {
      alert("Please enter a display name")
      return null
    }
    if (selectedArtifact && !hasUnsavedChanges) {
      return selectedArtifact
    }

    setSaving(true)
    try {
      if (mode === "create") {
        const created = await artifactsService.create(
          buildArtifactPayload(formData, artifactChatDraftKey),
          currentTenant?.slug,
        )
        await loadArtifactEditorState(created.id)
        router.replace(buildArtifactDetailHref(created.id), { scroll: false })
        return created
      }
      if (selectedArtifact) {
        const updatedArtifact = await artifactsService.update(
          selectedArtifact.id,
          buildArtifactUpdatePayload(formData, artifactChatDraftKey),
          currentTenant?.slug,
        )
        syncSelectedArtifact(updatedArtifact)
        await persistWorkingDraft(updatedArtifact.id)
        if (versionsOpen) {
          await loadArtifactVersions()
        }
        return updatedArtifact
      }
    } catch (error) {
      console.error("Failed to save artifact", error)
      alert(error instanceof Error ? error.message : "Failed to save artifact")
      return null
    } finally {
      setSaving(false)
    }
    return null
  }

  const handlePublish = useCallback(async (artifact: Artifact) => {
    if (!confirm(`Publish "${artifact.display_name}"?`)) return
    setPublishingId(artifact.id)
    try {
      await artifactsService.publish(artifact.id, currentTenant?.slug)
      const refreshed = await artifactsService.get(artifact.id, currentTenant?.slug)
      syncSelectedArtifact(refreshed)
      await persistWorkingDraft(refreshed.id)
      if (versionsOpen) {
        await loadArtifactVersions()
      }
    } catch (error) {
      console.error("Failed to publish artifact", error)
      alert(error instanceof Error ? error.message : "Publish failed")
    } finally {
      setPublishingId(null)
    }
  }, [currentTenant?.slug, loadArtifactVersions, persistWorkingDraft, syncSelectedArtifact, versionsOpen])

  const handlePublishFromEditorIgnoringWarnings = useCallback(async () => {
    if (!selectedArtifact) return
    if (hasUnsavedChanges) {
      const savedArtifact = await handleSave()
      if (!savedArtifact) return
      await handlePublish(savedArtifact)
      return
    }
    await handlePublish(selectedArtifact)
  }, [handlePublish, hasUnsavedChanges, selectedArtifact])

  const handlePublishFromEditor = useCallback(async () => {
    if (!selectedArtifact) return
    if (getArtifactLanguageWarningPaths(formData.language, formData.source_files).length > 0) {
      setPublishWarningOpen(true)
      return
    }
    await handlePublishFromEditorIgnoringWarnings()
  }, [formData.language, formData.source_files, handlePublishFromEditorIgnoringWarnings, selectedArtifact])

  const handleConvertKind = useCallback(async () => {
    if (!selectedArtifact) return
    if (convertTargetKind === formData.kind) return
    if (!confirm(`Convert "${selectedArtifact.display_name}" from ${kindLabel(formData.kind)} to ${kindLabel(convertTargetKind)}? Incompatible contract fields will be cleared.`)) {
      return
    }
    setConverting(true)
    try {
      const converted = await artifactsService.convertKind(
        selectedArtifact.id,
        buildConvertPayload(convertTargetKind, formData),
        currentTenant?.slug,
      )
      syncSelectedArtifact(converted)
      setFormData(formDataFromArtifact(converted))
      setConvertTargetKind(converted.kind === "agent_node" ? "rag_operator" : "agent_node")
    } catch (error) {
      console.error("Failed to convert artifact kind", error)
      alert(error instanceof Error ? error.message : "Convert kind failed")
    } finally {
      setConverting(false)
    }
  }, [convertTargetKind, currentTenant?.slug, formData, selectedArtifact, syncSelectedArtifact])

  const currentContractValue = useMemo(() => {
    if (formData.kind === "agent_node") return formData.agent_contract
    if (formData.kind === "rag_operator") return formData.rag_contract
    return formData.tool_contract
  }, [formData.agent_contract, formData.kind, formData.rag_contract, formData.tool_contract])

  const updateCurrentContract = useCallback((value: string) => {
    if (formData.kind === "agent_node") {
      updateFormData("agent_contract", value)
      return
    }
    if (formData.kind === "rag_operator") {
      updateFormData("rag_contract", value)
      return
    }
    updateFormData("tool_contract", value)
  }, [formData.kind, updateFormData])

  const testCapabilities = useMemo(() => {
    return tryParseObject(formData.capabilities, {
      network_access: false,
      allowed_hosts: [],
      secret_refs: [],
      storage_access: [],
      side_effects: [],
    }) as unknown as ArtifactCapabilityConfig
  }, [formData.capabilities])
  const testConfigSchema = useMemo(() => tryParseObject(formData.config_schema, { type: "object", properties: {} }), [formData.config_schema])
  const testAgentContract = useMemo(() => tryParseObject(formData.agent_contract, {}) as unknown as AgentArtifactContract, [formData.agent_contract])
  const testRagContract = useMemo(() => tryParseObject(formData.rag_contract, {}) as unknown as RAGArtifactContract, [formData.rag_contract])
  const testToolContract = useMemo(() => {
    try {
      return parseToolContract(formData.tool_contract)
    } catch {
      return null
    }
  }, [formData.tool_contract])

  const handleResolvedArtifactId = useCallback((resolvedArtifactId: string) => {
    if (!resolvedArtifactId || selectedArtifact?.id === resolvedArtifactId) {
      return
    }
    void (async () => {
      await loadArtifactEditorState(resolvedArtifactId)
      router.replace(buildArtifactDetailHref(resolvedArtifactId), { scroll: false })
    })()
  }, [loadArtifactEditorState, router, selectedArtifact?.id])

  const handlePromptFill = useCallback(async (_promptId: string, content: string) => {
    if (!promptMentionModal.context || formData.kind !== "tool_impl") {
      return
    }
    updateFormData("tool_contract", fillPromptMentionJsonToken(formData.tool_contract, promptMentionModal.context.tokenRange, content))
  }, [formData.kind, formData.tool_contract, promptMentionModal.context, updateFormData])

  const artifactCodingChat = useArtifactCodingChat({
    tenantSlug: currentTenant?.slug,
    tenantId: currentTenant?.id || null,
    artifactId: selectedArtifact?.id || null,
    draftKey: artifactChatDraftKey,
    isCreateMode: mode === "create" || !selectedArtifact?.id,
    getDraftSnapshot: () => workingDraftSnapshot,
    onApplyDraftSnapshot: applyDraftSnapshot,
    onResolvedArtifactId: handleResolvedArtifactId,
    onError: setChatError,
  })

  const renderEditor = () => (
    <div className="relative w-full min-w-0 flex-1 overflow-hidden">
      <ArtifactWorkspaceEditor
        language={formData.language}
        tenantSlug={currentTenant?.slug}
        dependencies={formData.dependencies}
        loading={loading}
        sourceFiles={formData.source_files}
        activeFilePath={activeFilePath}
        entryModulePath={formData.entry_module_path}
        onActiveFileChange={setActiveFilePath}
        onSourceFilesChange={(files) => updateFormData("source_files", files)}
        sidebarOpen={sidebarOpen}
        onSidebarOpenChange={setSidebarOpen}
        availableCredentials={availableCredentials}
        configContent={
          <ArtifactConfigPanel
            formData={formData}
            tenantSlug={currentTenant?.slug}
            selectedArtifact={selectedArtifact}
            viewMode={viewMode}
            convertTargetKind={convertTargetKind}
            converting={converting}
            currentContractValue={currentContractValue}
            onUpdateFormData={updateFormData}
            onUpdateCurrentContract={updateCurrentContract}
            onConvertTargetKindChange={setConvertTargetKind}
            onConvertKind={handleConvertKind}
            onPromptMentionClick={(promptId, tokenRange) => promptMentionModal.openPromptMentionModal(promptId, { tokenRange })}
          />
        }
      />
    </div>
  )

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <Dialog open={publishWarningOpen} onOpenChange={setPublishWarningOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Publish with opposite-language code files?</DialogTitle>
            <DialogDescription>
              This artifact contains code files from the opposite language lane. Non-code files are fine and will be ignored here. These opposite-language code files will stay on the artifact, but they are not valid code for the active runtime lane.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            {getArtifactLanguageWarningPaths(formData.language, formData.source_files).map((path) => (
              <div key={path} className="rounded-md border px-3 py-2 text-muted-foreground">
                {path}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishWarningOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => { setPublishWarningOpen(false); void handlePublishFromEditorIgnoringWarnings() }}>
              Publish anyway
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ArtifactEditorHeader
        viewMode={viewMode}
        displayName={loading ? (mode === "edit" ? "Edit Artifact" : "New Artifact") : formData.display_name}
        controlsDisabled={loading}
        sidebarOpen={sidebarOpen}
        isAgentPanelOpen={artifactCodingChat.isAgentPanelOpen}
        isPublishing={publishingId === selectedArtifact?.id}
        isPublished={Boolean(mode === "edit" && selectedArtifact?.type === "published" && selectedArtifact.owner_type === "tenant")}
        isSaving={saving}
        disableSave={false}
        showPublish={Boolean(mode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant")}
        showVersions={Boolean(mode === "edit" && selectedArtifact?.id)}
        versionsOpen={versionsOpen}
        artifactVersions={artifactVersions}
        versionsLoading={loadingVersions}
        applyingRevisionId={applyingRevisionId}
        hasUnsavedChanges={hasUnsavedChanges}
        onRefreshArtifacts={() => {}}
        onCreateArtifact={(kind, language) => {
          router.push(buildArtifactNewHref({ kind, language }))
        }}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        onToggleAgentPanel={() => artifactCodingChat.setIsAgentPanelOpen(!artifactCodingChat.isAgentPanelOpen)}
        onStartNewChat={artifactCodingChat.startNewChat}
        onOpenChatHistory={() => {
          void artifactCodingChat.refreshChatSessions()
          setIsChatHistoryOpen(true)
        }}
        onVersionsOpenChange={setVersionsOpen}
        onSelectVersion={(revisionId) => {
          void applyArtifactVersion(revisionId)
        }}
        onPublish={() => {
          void handlePublishFromEditor()
        }}
        onRunTest={() => document.getElementById("artifact-test-panel-execute")?.click()}
        onSave={() => {
          void handleSave()
        }}
      />
      <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
        <div className="relative flex min-h-0 w-full flex-1 overflow-hidden">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {renderEditor()}
            </div>
            <ArtifactTestPanel
              tenantSlug={currentTenant?.slug}
              artifactId={selectedArtifact?.id}
              controlsDisabled={loading}
              sourceFiles={formData.source_files}
              entryModulePath={formData.entry_module_path}
              language={formData.language}
              kind={formData.kind}
              runtimeTarget={formData.runtime_target}
              capabilities={testCapabilities}
              configSchema={testConfigSchema}
              agentContract={formData.kind === "agent_node" ? testAgentContract : undefined}
              ragContract={formData.kind === "rag_operator" ? testRagContract : undefined}
              toolContract={formData.kind === "tool_impl" ? testToolContract : undefined}
              agentPanelOpen={artifactCodingChat.isAgentPanelOpen}
            />
          </div>
          {artifactCodingChat.isAgentPanelOpen ? (
            <div
              className="w-[1.5px] shrink-0 bg-gradient-to-b from-transparent via-primary to-transparent"
              style={{ opacity: 0.16, height: "calc(100% - 50px)" }}
            />
          ) : null}
          <ArtifactCodingChatPanel
            isOpen={artifactCodingChat.isAgentPanelOpen}
            controlsDisabled={loading}
            isSending={artifactCodingChat.isSending}
            isStopping={artifactCodingChat.isStopping}
            timeline={artifactCodingChat.timeline}
            activeThinkingSummary={artifactCodingChat.activeThinkingSummary}
            activeContextStatus={artifactCodingChat.activeContextStatus}
            chatSessions={artifactCodingChat.chatSessions}
            isHistoryOpen={isChatHistoryOpen}
            onHistoryOpenChange={setIsChatHistoryOpen}
            onLoadChatSession={artifactCodingChat.loadChatSession}
            onSendMessage={artifactCodingChat.sendMessage}
            onStopRun={artifactCodingChat.stopCurrentRun}
            chatModels={artifactCodingChat.chatModels}
            selectedRunModelLabel={artifactCodingChat.selectedRunModelLabel}
            isModelSelectorOpen={artifactCodingChat.isModelSelectorOpen}
            onModelSelectorOpenChange={artifactCodingChat.setIsModelSelectorOpen}
            onSelectModelId={artifactCodingChat.setSelectedRunModelId}
            pendingQuestion={artifactCodingChat.pendingQuestion}
            isAnsweringQuestion={artifactCodingChat.isAnsweringQuestion}
            runningSessionIds={artifactCodingChat.runningSessionIds}
            hasOlderHistory={artifactCodingChat.hasOlderHistory}
            isLoadingOlderHistory={artifactCodingChat.isLoadingOlderHistory}
            onLoadOlderHistory={artifactCodingChat.loadOlderHistory}
            onAnswerQuestion={artifactCodingChat.answerPendingQuestion}
            revertingRunId={artifactCodingChat.revertingRunId}
            onRevertToRun={artifactCodingChat.revertToRun}
          />
        </div>
      </div>
      {chatError ? (
        <div className="pointer-events-none fixed bottom-4 right-4 z-50 w-full max-w-md px-4 sm:px-0">
          <Card className="pointer-events-auto border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive shadow-lg">
            {chatError}
          </Card>
        </div>
      ) : null}
      <PromptModal
        promptId={promptMentionModal.promptId}
        open={promptMentionModal.open}
        onOpenChange={promptMentionModal.handleOpenChange}
        onFill={handlePromptFill}
      />
    </div>
  )
}
