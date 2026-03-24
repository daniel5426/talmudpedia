"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { AgentArtifactContract, Artifact, ArtifactCapabilityConfig, ArtifactKind, ArtifactVersionListItem, RAGArtifactContract, ToolArtifactContract, artifactsService } from "@/services/artifacts"
import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"
import { fillPromptMentionJsonToken } from "@/components/shared/PromptMentionJsonEditor"
import { PromptModal } from "@/components/shared/PromptModal"
import { usePromptMentionModal } from "@/components/shared/usePromptMentionModal"
import { ArtifactEditorHeader } from "@/components/admin/artifacts/ArtifactEditorHeader"
import { ArtifactConfigPanel } from "@/components/admin/artifacts/ArtifactConfigPanel"
import { ArtifactListView } from "@/components/admin/artifacts/ArtifactListView"
import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"
import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"
import { ArtifactCodingChatPanel } from "@/features/artifact-coding/ArtifactCodingChatPanel"
import { useArtifactCodingChat } from "@/features/artifact-coding/useArtifactCodingChat"
import { ArtifactFormData, createFormDataForKind, initialFormData } from "@/components/admin/artifacts/artifactEditorState"
import { buildArtifactPayload, buildArtifactUpdatePayload, buildConvertPayload, formDataFromArtifact, formDataFromDraftSnapshot, formDataFromArtifactVersion, kindLabel, serializeArtifactFormData, tryParseObject } from "@/components/admin/artifacts/artifactPageUtils"
import { Loader2 } from "lucide-react"
import { credentialsService, IntegrationCredential } from "@/services"

type ViewMode = "list" | "create" | "edit"
const ARTIFACT_CODING_DRAFT_KEY_STORAGE_KEY = "artifact-coding-agent:create-draft-key"
const PAGE_ARTIFACT_KIND_OPTIONS: Array<{ value: ArtifactKind; label: string }> = [
    { value: "agent_node", label: "Agent Node" },
    { value: "rag_operator", label: "RAG Operator" },
    { value: "tool_impl", label: "Tool Implementation" },
]

function getDefaultActiveFilePath(formData: ArtifactFormData): string {
    return formData.entry_module_path || formData.source_files[0]?.path || "__CONFIG__"
}

export default function ArtifactsPage() {
    const { currentTenant } = useTenant()
    const router = useRouter()
    const searchParams = useSearchParams()
    const modeParam = searchParams.get("mode") as ViewMode | null
    const idParam = searchParams.get("id")
    const kindParam = searchParams.get("kind") as ArtifactKind | null

    const [viewMode, setViewMode] = useState<ViewMode>("list")
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [publishingId, setPublishingId] = useState<string | null>(null)
    const [converting, setConverting] = useState(false)
    const [artifacts, setArtifacts] = useState<Artifact[]>([])
    const [availableCredentials, setAvailableCredentials] = useState<IntegrationCredential[]>([])
    const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
    const [formData, setFormData] = useState<ArtifactFormData>(initialFormData)
    const [convertTargetKind, setConvertTargetKind] = useState<ArtifactKind>("rag_operator")
    const [activeFilePath, setActiveFilePath] = useState(() => getDefaultActiveFilePath(initialFormData))
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [artifactChatDraftKey, setArtifactChatDraftKey] = useState("")
    const [chatError, setChatError] = useState<string | null>(null)
    const [versionsOpen, setVersionsOpen] = useState(false)
    const [artifactVersions, setArtifactVersions] = useState<ArtifactVersionListItem[]>([])
    const [loadingVersions, setLoadingVersions] = useState(false)
    const [applyingRevisionId, setApplyingRevisionId] = useState<string | null>(null)
    const promptMentionModal = usePromptMentionModal<{ tokenRange: { from: number; to: number } }>()
    const lastWorkingDraftSignatureRef = useRef<string | null>(null)
    const workingDraftSaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    useEffect(() => {
        if (typeof window === "undefined") return
        const existing = window.localStorage.getItem(ARTIFACT_CODING_DRAFT_KEY_STORAGE_KEY)
        if (existing) {
            setArtifactChatDraftKey(existing)
            return
        }
        const nextKey = crypto.randomUUID()
        window.localStorage.setItem(ARTIFACT_CODING_DRAFT_KEY_STORAGE_KEY, nextKey)
        setArtifactChatDraftKey(nextKey)
    }, [])

    const persistNewDraftKey = useCallback(() => {
        if (typeof window === "undefined") return
        const nextKey = crypto.randomUUID()
        window.localStorage.setItem(ARTIFACT_CODING_DRAFT_KEY_STORAGE_KEY, nextKey)
        setArtifactChatDraftKey(nextKey)
    }, [])

    const fetchArtifacts = useCallback(async (options?: { showLoading?: boolean }) => {
        if (options?.showLoading) {
            setLoading(true)
        }
        try {
            const data = await artifactsService.list(currentTenant?.slug)
            setArtifacts(data)
        } catch (error) {
            console.error("Failed to fetch artifacts", error)
        } finally {
            if (options?.showLoading) {
                setLoading(false)
            }
        }
    }, [currentTenant?.slug])

    const fetchAvailableCredentials = useCallback(async () => {
        try {
            const items = await credentialsService.listCredentials()
            setAvailableCredentials(items)
        } catch (error) {
            console.error("Failed to fetch integration credentials", error)
        }
    }, [])

    const syncSelectedArtifact = useCallback((artifact: Artifact) => {
        setSelectedArtifact(artifact)
        setConvertTargetKind(artifact.kind === "agent_node" ? "rag_operator" : "agent_node")
    }, [])

    const loadArtifactEditorState = useCallback(async (artifactId: string) => {
        const fullArtifact = await artifactsService.get(artifactId, currentTenant?.slug)
        let nextFormData = formDataFromArtifact(fullArtifact)
        try {
            const workingDraft = await artifactsService.getWorkingDraft(artifactId, currentTenant?.slug)
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

    useEffect(() => {
        void fetchArtifacts({ showLoading: true })
    }, [fetchArtifacts])

    useEffect(() => {
        void fetchAvailableCredentials()
    }, [fetchAvailableCredentials])

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

    const setViewModeWithUrl = useCallback((mode: ViewMode, id?: string) => {
        const params = new URLSearchParams()
        if (mode !== "list") params.set("mode", mode)
        if (id) params.set("id", id)
        const queryString = params.toString()
        router.push(`/admin/artifacts${queryString ? `?${queryString}` : ""}`)
        setViewMode(mode)
    }, [router])

    const handleCreate = useCallback((kind: ArtifactKind) => {
        const next = createFormDataForKind(kind)
        setFormData(next)
        setSelectedArtifact(null)
        setActiveFilePath(getDefaultActiveFilePath(next))
        setConvertTargetKind(kind === "agent_node" ? "rag_operator" : "agent_node")
        setViewModeWithUrl("create")
        persistNewDraftKey()
    }, [persistNewDraftKey, setViewModeWithUrl])

    const handleEdit = useCallback(async (artifact: Artifact) => {
        await loadArtifactEditorState(artifact.id)
        setViewMode("edit")
    }, [loadArtifactEditorState])

    const hydrateCreateMode = useCallback((kind: ArtifactKind) => {
        const next = createFormDataForKind(kind)
        setFormData(next)
        setSelectedArtifact(null)
        setActiveFilePath(getDefaultActiveFilePath(next))
        setConvertTargetKind(kind === "agent_node" ? "rag_operator" : "agent_node")
        setViewMode("create")
    }, [])

    useEffect(() => {
        if (loading) return
        if (modeParam === "edit" && idParam) {
            const artifact = artifacts.find((item) => item.id === idParam)
            if (artifact) {
                handleEdit(artifact)
            } else {
                setViewModeWithUrl("list")
            }
            return
        }
        if (modeParam === "create") {
            const requestedKind = kindParam && PAGE_ARTIFACT_KIND_OPTIONS.some((option) => option.value === kindParam)
                ? kindParam
                : "agent_node"
            hydrateCreateMode(requestedKind)
            return
        }
        setViewMode("list")
    }, [artifacts, handleEdit, hydrateCreateMode, idParam, kindParam, loading, modeParam, setViewModeWithUrl])

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

    useEffect(() => {
        if (!versionsOpen || !selectedArtifact?.id) return
        void loadArtifactVersions()
    }, [loadArtifactVersions, selectedArtifact?.id, versionsOpen])

    useEffect(() => {
        if (viewMode !== "edit") {
            setVersionsOpen(false)
            setArtifactVersions([])
        }
    }, [viewMode])

    const persistWorkingDraft = useCallback(async (artifactId: string, snapshot = workingDraftSnapshot, signature = currentFormSignature) => {
        if (workingDraftSaveTimeoutRef.current) {
            clearTimeout(workingDraftSaveTimeoutRef.current)
            workingDraftSaveTimeoutRef.current = null
        }
        await artifactsService.updateWorkingDraft(
            artifactId,
            {
                artifact_id: artifactId,
                draft_key: artifactChatDraftKey || undefined,
                draft_snapshot: snapshot,
            },
            currentTenant?.slug,
        )
        lastWorkingDraftSignatureRef.current = signature
    }, [artifactChatDraftKey, currentFormSignature, currentTenant?.slug, workingDraftSnapshot])

    useEffect(() => {
        if (workingDraftSaveTimeoutRef.current) {
            clearTimeout(workingDraftSaveTimeoutRef.current)
            workingDraftSaveTimeoutRef.current = null
        }
        if (viewMode !== "edit" || !selectedArtifact?.id) {
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
    }, [currentFormSignature, persistWorkingDraft, selectedArtifact?.id, viewMode])

    const updateFormData = useCallback((field: keyof ArtifactFormData, value: string | ArtifactKind | ArtifactFormData["source_files"]) => {
        setFormData((prev) => {
            return { ...prev, [field]: value }
        })
    }, [])

    const applyDraftSnapshot = useCallback((snapshot: Record<string, unknown>) => {
        setFormData((prev) => ({
            display_name: typeof snapshot.display_name === "string" ? snapshot.display_name : prev.display_name,
            description: typeof snapshot.description === "string" ? snapshot.description : prev.description,
            kind: (typeof snapshot.kind === "string" ? snapshot.kind : prev.kind) as ArtifactKind,
            source_files: Array.isArray(snapshot.source_files)
                ? snapshot.source_files as ArtifactFormData["source_files"]
                : prev.source_files,
            entry_module_path: typeof snapshot.entry_module_path === "string" ? snapshot.entry_module_path : prev.entry_module_path,
            python_dependencies: typeof snapshot.python_dependencies === "string" ? snapshot.python_dependencies : prev.python_dependencies,
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
        setActiveFilePath(formData.entry_module_path || formData.source_files[0]?.path || "__CONFIG__")
    }, [activeFilePath, formData.entry_module_path, formData.source_files])

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
            if (viewMode === "create") {
                const created = await artifactsService.create(buildArtifactPayload(formData), currentTenant?.slug)
                await fetchArtifacts()
                setViewModeWithUrl("edit", created.id)
                return created
            } else if (selectedArtifact) {
                const updatedArtifact = await artifactsService.update(selectedArtifact.id, buildArtifactUpdatePayload(formData), currentTenant?.slug)
                syncSelectedArtifact(updatedArtifact)
                await persistWorkingDraft(updatedArtifact.id)
                await fetchArtifacts()
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

    const handleDelete = async (artifact: Artifact) => {
        if (!confirm(`Delete "${artifact.display_name}"?`)) return
        try {
            await artifactsService.delete(artifact.id, currentTenant?.slug)
            if (selectedArtifact?.id === artifact.id) {
                setSelectedArtifact(null)
                setViewModeWithUrl("list")
            }
            await fetchArtifacts()
        } catch (error) {
            console.error("Failed to delete artifact", error)
            alert("Failed to delete artifact")
        }
    }

    const handlePublish = async (artifact: Artifact) => {
        if (!confirm(`Publish "${artifact.display_name}"?`)) return
        setPublishingId(artifact.id)
        try {
            await artifactsService.publish(artifact.id, currentTenant?.slug)
            await fetchArtifacts()
            if (selectedArtifact?.id === artifact.id) {
                const refreshed = await artifactsService.get(artifact.id, currentTenant?.slug)
                syncSelectedArtifact(refreshed)
                await persistWorkingDraft(refreshed.id)
                if (versionsOpen) {
                    await loadArtifactVersions()
                }
            }
        } catch (error) {
            console.error("Failed to publish artifact", error)
            alert(error instanceof Error ? error.message : "Publish failed")
        } finally {
            setPublishingId(null)
        }
    }

    const handlePublishFromEditor = async () => {
        if (!selectedArtifact) return
        if (hasUnsavedChanges) {
            const savedArtifact = await handleSave()
            if (!savedArtifact) return
            await handlePublish(savedArtifact)
            return
        }
        await handlePublish(selectedArtifact)
    }

    const handleConvertKind = async () => {
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
                currentTenant?.slug
            )
            syncSelectedArtifact(converted)
            setFormData(formDataFromArtifact(converted))
            setConvertTargetKind(converted.kind === "agent_node" ? "rag_operator" : "agent_node")
            await fetchArtifacts()
        } catch (error) {
            console.error("Failed to convert artifact kind", error)
            alert(error instanceof Error ? error.message : "Convert kind failed")
        } finally {
            setConverting(false)
        }
    }

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

    const renderEditor = () => (
        <div className="relative w-full min-w-0 flex-1 overflow-hidden">
            <ArtifactWorkspaceEditor
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
    const testToolContract = useMemo(() => tryParseObject(formData.tool_contract, {}) as unknown as ToolArtifactContract, [formData.tool_contract])
    const handleResolvedArtifactId = useCallback((resolvedArtifactId: string) => {
        if (!resolvedArtifactId || selectedArtifact?.id === resolvedArtifactId) {
            return
        }
        void (async () => {
            await loadArtifactEditorState(resolvedArtifactId)
            setViewModeWithUrl("edit", resolvedArtifactId)
        })()
    }, [loadArtifactEditorState, selectedArtifact?.id, setViewModeWithUrl])
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
        isCreateMode: viewMode === "create" || !selectedArtifact?.id,
        getDraftSnapshot: () => workingDraftSnapshot,
        onApplyDraftSnapshot: applyDraftSnapshot,
        onResolvedArtifactId: handleResolvedArtifactId,
        onError: setChatError,
    })

    if (loading) {
        return (
            <div className="w-full space-y-6 p-8">
                <div className="flex items-center gap-4">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <div className="space-y-2">
                        <Skeleton className="h-6 w-48" />
                        <Skeleton className="h-4 w-64" />
                    </div>
                </div>
                <Card className="flex items-center justify-center p-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
                </Card>
            </div>
        )
    }

    return (
        <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
            <ArtifactEditorHeader
                viewMode={viewMode}
                displayName={formData.display_name}
                sidebarOpen={sidebarOpen}
                isAgentPanelOpen={artifactCodingChat.isAgentPanelOpen}
                isPublishing={publishingId === selectedArtifact?.id}
                isSaving={saving}
                disableSave={false}
                showPublish={Boolean(viewMode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant")}
                showVersions={Boolean(viewMode === "edit" && selectedArtifact?.id)}
                versionsOpen={versionsOpen}
                artifactVersions={artifactVersions}
                versionsLoading={loadingVersions}
                applyingRevisionId={applyingRevisionId}
                hasUnsavedChanges={hasUnsavedChanges}
                onRefreshArtifacts={fetchArtifacts}
                onCreateArtifact={handleCreate}
                onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
                onToggleAgentPanel={() => artifactCodingChat.setIsAgentPanelOpen(!artifactCodingChat.isAgentPanelOpen)}
                onVersionsOpenChange={setVersionsOpen}
                onSelectVersion={(revisionId) => {
                    void applyArtifactVersion(revisionId)
                }}
                onPublish={handlePublishFromEditor}
                onRunTest={() => document.getElementById("artifact-test-panel-execute")?.click()}
                onSave={() => {
                    void handleSave()
                }}
            />
            <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
                {viewMode === "list" ? (
                    <div className="h-full overflow-auto" data-admin-page-scroll>
                        <ArtifactListView
                            artifacts={artifacts}
                            publishingId={publishingId}
                            onEditArtifact={(artifact) => setViewModeWithUrl("edit", artifact.id)}
                            onDeleteArtifact={(artifact) => {
                                void handleDelete(artifact)
                            }}
                            onPublishArtifact={(artifact) => {
                                void handlePublish(artifact)
                            }}
                        />
                    </div>
                ) : (
                    <div className="relative flex min-h-0 w-full flex-1 overflow-hidden">
                        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                                {renderEditor()}
                            </div>
                            <ArtifactTestPanel
                                tenantSlug={currentTenant?.slug}
                                artifactId={selectedArtifact?.id}
                                sourceFiles={formData.source_files}
                                entryModulePath={formData.entry_module_path}
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
                        {artifactCodingChat.isAgentPanelOpen && (
                            <div
                                className="w-[1.5px] bg-gradient-to-b from-transparent via-primary to-transparent shrink-0"
                                style={{ 
                                    opacity: 0.16,
                                    height: "calc(100% - 50px)"
                                }}
                            />
                        )}
                        <ArtifactCodingChatPanel
                            isOpen={artifactCodingChat.isAgentPanelOpen}
                            isSending={artifactCodingChat.isSending}
                            isStopping={artifactCodingChat.isStopping}
                            timeline={artifactCodingChat.timeline}
                            activeThinkingSummary={artifactCodingChat.activeThinkingSummary}
                            chatSessions={artifactCodingChat.chatSessions}
                            activeChatSessionId={artifactCodingChat.activeChatSessionId}
                            onStartNewChat={artifactCodingChat.startNewChat}
                            onOpenHistory={() => {
                                void artifactCodingChat.refreshChatSessions()
                            }}
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
                )}
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
