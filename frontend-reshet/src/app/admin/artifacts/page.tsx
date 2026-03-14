"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import {
    AgentArtifactContract,
    Artifact,
    ArtifactCapabilityConfig,
    ArtifactKind,
    RAGArtifactContract,
    ToolArtifactContract,
    artifactsService,
} from "@/services/artifacts"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { KesherLogo } from "@/components/kesher-logo"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { JsonEditor } from "@/components/ui/json-editor"
import { Textarea } from "@/components/ui/textarea"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"
import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"
import { ArtifactCodingChatPanel } from "@/features/artifact-coding/ArtifactCodingChatPanel"
import { useArtifactCodingChat } from "@/features/artifact-coding/useArtifactCodingChat"
import {
    ARTIFACT_KIND_OPTIONS,
    ArtifactFormData,
    createFormDataForKind,
    initialFormData,
    RUNTIME_TARGET_OPTIONS,
} from "@/components/admin/artifacts/artifactEditorState"
import {
    buildArtifactPayload,
    buildArtifactUpdatePayload,
    buildConvertPayload,
    contractEditorTitle,
    formDataFromArtifact,
    kindLabel,
    slugify,
    tryParseObject,
} from "@/components/admin/artifacts/artifactPageUtils"
import {
    Bot,
    Database,
    ChevronDown,
    Edit,
    Loader2,
    Package,
    PanelLeft,
    Play,
    Plus,
    RefreshCw,
    Save,
    Trash2,
    Upload,
    Wrench,
} from "lucide-react"

type ViewMode = "list" | "create" | "edit"
const ARTIFACT_CODING_DRAFT_KEY_STORAGE_KEY = "artifact-coding-agent:create-draft-key"

function getDefaultActiveFilePath(formData: ArtifactFormData): string {
    return formData.entry_module_path || formData.source_files[0]?.path || "__CONFIG__"
}

function kindIcon(kind: ArtifactKind) {
    if (kind === "agent_node") return Bot
    if (kind === "rag_operator") return Database
    return Wrench
}

export default function ArtifactsPage() {
    const { currentTenant } = useTenant()
    const router = useRouter()
    const searchParams = useSearchParams()
    const modeParam = searchParams.get("mode") as ViewMode | null
    const idParam = searchParams.get("id")

    const [viewMode, setViewMode] = useState<ViewMode>("list")
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [publishingId, setPublishingId] = useState<string | null>(null)
    const [converting, setConverting] = useState(false)
    const [artifacts, setArtifacts] = useState<Artifact[]>([])
    const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
    const [formData, setFormData] = useState<ArtifactFormData>(initialFormData)
    const [convertTargetKind, setConvertTargetKind] = useState<ArtifactKind>("rag_operator")
    const [isSlugManuallyEdited, setIsSlugManuallyEdited] = useState(false)
    const [slugError, setSlugError] = useState<string | null>(null)
    const [activeFilePath, setActiveFilePath] = useState(() => getDefaultActiveFilePath(initialFormData))
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [artifactChatDraftKey, setArtifactChatDraftKey] = useState("")
    const [chatError, setChatError] = useState<string | null>(null)

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

    const reloadArtifact = useCallback(async (artifactId: string) => {
        const fullArtifact = await artifactsService.get(artifactId, currentTenant?.slug)
        setSelectedArtifact(fullArtifact)
        setFormData(formDataFromArtifact(fullArtifact))
        setConvertTargetKind(fullArtifact.kind === "agent_node" ? "rag_operator" : "agent_node")
        return fullArtifact
    }, [currentTenant?.slug])

    useEffect(() => {
        fetchArtifacts()
    }, [fetchArtifacts])

    const checkSlugCollision = useCallback((slug: string) => {
        return artifacts.some((artifact) => artifact.slug === slug && artifact.id !== selectedArtifact?.id)
    }, [artifacts, selectedArtifact?.id])

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
        setIsSlugManuallyEdited(false)
        setSlugError(null)
        setConvertTargetKind(kind === "agent_node" ? "rag_operator" : "agent_node")
        setViewModeWithUrl("create")
        persistNewDraftKey()
    }, [persistNewDraftKey, setViewModeWithUrl])

    const handleEdit = useCallback(async (artifact: Artifact) => {
        const fullArtifact = await artifactsService.get(artifact.id, currentTenant?.slug)
        const nextFormData = formDataFromArtifact(fullArtifact)
        setSelectedArtifact(fullArtifact)
        setFormData(nextFormData)
        setActiveFilePath(getDefaultActiveFilePath(nextFormData))
        setIsSlugManuallyEdited(true)
        setSlugError(null)
        setConvertTargetKind(fullArtifact.kind === "agent_node" ? "rag_operator" : "agent_node")
        setViewMode("edit")
    }, [currentTenant?.slug])

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
        setViewMode("list")
    }, [artifacts, handleEdit, idParam, loading, modeParam, setViewModeWithUrl])

    const updateFormData = useCallback((field: keyof ArtifactFormData, value: string | ArtifactKind | ArtifactFormData["source_files"]) => {
        setFormData((prev) => {
            const updated = { ...prev, [field]: value }
            if (field === "display_name" && !isSlugManuallyEdited) {
                updated.slug = slugify(String(value))
            }
            if (field === "slug") {
                setIsSlugManuallyEdited(true)
            }
            if (field === "slug" || (field === "display_name" && !isSlugManuallyEdited)) {
                const nextSlug = field === "slug" ? String(value) : slugify(String(value))
                setSlugError(nextSlug && checkSlugCollision(nextSlug) ? "Slug already exists" : null)
            }
            return updated
        })
    }, [checkSlugCollision, isSlugManuallyEdited])

    const applyDraftSnapshot = useCallback((snapshot: Record<string, unknown>) => {
        setFormData((prev) => ({
            slug: typeof snapshot.slug === "string" ? snapshot.slug : prev.slug,
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

    const handleSave = async () => {
        if (!formData.display_name.trim()) {
            alert("Please enter a display name")
            return
        }
        if (!formData.slug.trim()) {
            alert("Please enter a slug")
            return
        }
        if (slugError) {
            alert(slugError)
            return
        }

        setSaving(true)
        try {
            if (viewMode === "create") {
                const created = await artifactsService.create(buildArtifactPayload(formData), currentTenant?.slug)
                await fetchArtifacts()
                setViewModeWithUrl("edit", created.id)
            } else if (selectedArtifact) {
                await artifactsService.update(selectedArtifact.id, buildArtifactUpdatePayload(formData), currentTenant?.slug)
                await reloadArtifact(selectedArtifact.id)
                await fetchArtifacts()
            }
        } catch (error) {
            console.error("Failed to save artifact", error)
            alert(error instanceof Error ? error.message : "Failed to save artifact")
        } finally {
            setSaving(false)
        }
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
                await reloadArtifact(artifact.id)
            }
        } catch (error) {
            console.error("Failed to publish artifact", error)
            alert(error instanceof Error ? error.message : "Publish failed")
        } finally {
            setPublishingId(null)
        }
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
            setSelectedArtifact(converted)
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

    const renderHeader = () => (
        <AdminPageHeader contentClassName="h-12 items-center">
            <div className="flex min-w-0 flex-1 items-center gap-3">
                <CustomBreadcrumb
                    items={[
                        { label: "Artifacts", href: "/admin/artifacts", active: viewMode === "list" },
                        ...(viewMode === "create" ? [{ label: "New Artifact", active: true }] : []),
                        ...(viewMode === "edit" ? [{ label: formData.display_name || "Edit Artifact", active: true }] : []),
                    ]}
                />
            </div>
            {viewMode === "list" ? (
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={fetchArtifacts}>
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Refresh
                    </Button>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button size="sm">
                                <Plus className="mr-2 h-4 w-4" />
                                New Artifact
                                <ChevronDown className="ml-1 h-4 w-4 opacity-50" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-64">
                            <DropdownMenuLabel>Select Artifact Type</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            {ARTIFACT_KIND_OPTIONS.map((option) => {
                                const Icon = kindIcon(option.value)
                                return (
                                    <DropdownMenuItem
                                        key={option.value}
                                        className="flex cursor-pointer flex-col items-start gap-1 py-3"
                                        onClick={() => handleCreate(option.value)}
                                    >
                                        <div className="flex items-center gap-2 font-medium text-foreground">
                                            <Icon className="h-4 w-4 text-muted-foreground" />
                                            <span>{option.label}</span>
                                        </div>
                                        <span className="text-[11px] leading-tight text-muted-foreground">
                                            {option.description}
                                        </span>
                                    </DropdownMenuItem>
                                )
                            })}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            ) : (
                <div className="flex items-center gap-2">
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setSidebarOpen((prev) => !prev)}
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                        title={sidebarOpen ? "Hide file explorer" : "Show file explorer"}
                    >
                        <PanelLeft className="!size-[17px]" />
                    </Button>
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => artifactCodingChat.setIsAgentPanelOpen(!artifactCodingChat.isAgentPanelOpen)}
                        className="h-8 w-8 mr-1 text-muted-foreground hover:text-foreground"
                        title={artifactCodingChat.isAgentPanelOpen ? "Close coding agent panel" : "Open coding agent panel"}
                    >
                        <KesherLogo
                            size={23}
                            className={cn(
                                "h-4 w-4 transition-transform duration-200",
                                artifactCodingChat.isAgentPanelOpen
                                    ? "rotate-90 text-foreground"
                                    : "text-sky-600"
                            )}
                        />
                    </Button>
                    {viewMode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant" && (
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePublish(selectedArtifact)}
                            disabled={publishingId === selectedArtifact.id}
                        >
                            {publishingId === selectedArtifact.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                            Publish
                        </Button>
                    )}
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => document.getElementById("artifact-test-panel-execute")?.click()}
                    >
                        <Play className="mr-2 h-4 w-4 fill-current" />
                        Test
                    </Button>
                    <Button size="sm" onClick={handleSave} disabled={saving || !!slugError}>
                        {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                        Save
                    </Button>
                </div>
            )}
        </AdminPageHeader>
    )

    const renderList = () => (
        <div className="m-4 space-y-3">
            <div>
                <h2 className="text-lg font-semibold">Unified artifact runtime</h2>
                <p className="text-sm text-muted-foreground">One execution substrate with explicit domain kinds.</p>
            </div>
            <div className="rounded-xl border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Artifact</TableHead>
                            <TableHead>Kind</TableHead>
                            <TableHead>Owner</TableHead>
                            <TableHead>Version</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {artifacts.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={5} className="py-12 text-center text-muted-foreground">
                                    <div className="flex flex-col items-center gap-2">
                                        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                                            <Package className="h-6 w-6" />
                                        </div>
                                        <span>No artifacts found.</span>
                                    </div>
                                </TableCell>
                            </TableRow>
                        ) : (
                            artifacts.map((artifact) => {
                                const Icon = kindIcon(artifact.kind)
                                return (
                                    <TableRow key={artifact.id}>
                                        <TableCell className="font-medium">
                                            <div className="flex items-center gap-3">
                                                <div className="rounded-lg bg-muted p-2">
                                                    <Icon className="h-4 w-4" />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span>{artifact.display_name}</span>
                                                    <span className="font-mono text-xs text-muted-foreground">{artifact.slug}</span>
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline">{kindLabel(artifact.kind)}</Badge>
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant={artifact.owner_type === "system" ? "secondary" : "outline"}>{artifact.owner_type}</Badge>
                                        </TableCell>
                                        <TableCell className="text-sm text-muted-foreground">{artifact.version}</TableCell>
                                        <TableCell className="text-right">
                                            <div className="flex justify-end gap-1">
                                                {artifact.type === "draft" && artifact.owner_type === "tenant" && (
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        title="Publish"
                                                        onClick={() => handlePublish(artifact)}
                                                        disabled={publishingId === artifact.id}
                                                    >
                                                        {publishingId === artifact.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                                                    </Button>
                                                )}
                                                <Button variant="ghost" size="icon" onClick={() => setViewModeWithUrl("edit", artifact.id)}>
                                                    <Edit className="h-4 w-4" />
                                                </Button>
                                                {artifact.owner_type === "tenant" && (
                                                    <Button variant="ghost" size="icon" onClick={() => handleDelete(artifact)}>
                                                        <Trash2 className="h-4 w-4 text-destructive" />
                                                    </Button>
                                                )}
                                            </div>
                                        </TableCell>
                                    </TableRow>
                                )
                            })
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    )

    const renderConfigContent = () => (
        <div className="flex h-full w-full flex-col overflow-y-auto bg-background [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-border">
            <div className="mx-auto w-full max-w-5xl px-6 py-12 md:px-12">
                <div className="mb-12">
                    <h2 className="text-xl font-medium tracking-tight">Configuration Profile</h2>
                    <p className="mt-1 text-sm text-muted-foreground/80">Properties, runtime targets, and boundary definitions.</p>
                </div>

                <div className="grid grid-cols-1 gap-x-5 gap-y-12 lg:grid-cols-2">
                    {/* Identity Block */}
                    <div className="space-y-6">
                        <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                            <span className="mr-3 text-primary">01</span> Identity
                        </h3>

                        <div className="group relative">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Display Name</Label>
                            <input
                                value={formData.display_name}
                                onChange={(e) => updateFormData("display_name", e.target.value)}
                                className="w-full rounded-md border border-border/40 bg-transparent px-3 py-2 text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                                placeholder="e.g. Data Extractor Agent"
                            />
                        </div>

                        <div className="group relative">
                            <div className="mb-2 flex items-center justify-between">
                                <Label className="text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">System Slug</Label>
                                {slugError && <span className="text-[10px] font-medium text-destructive">{slugError}</span>}
                            </div>
                            <input
                                value={formData.slug}
                                onChange={(e) => updateFormData("slug", e.target.value)}
                                className={cn(
                                    "w-full rounded-md border border-border/40 bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0",
                                    slugError && "border-destructive text-destructive"
                                )}
                            />
                        </div>

                        <div className="group relative">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Artifact Type</Label>
                            <div className="flex h-[38px] w-full items-center rounded-md border border-border/40 bg-transparent px-3">
                                <span className="text-sm">{kindLabel(formData.kind)}</span>
                            </div>
                        </div>

                        <div className="group relative pt-2">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Description</Label>
                            <Textarea
                                value={formData.description}
                                onChange={(e) => updateFormData("description", e.target.value)}
                                rows={3}
                                placeholder="Briefly describe the artifact's purpose..."
                                className="w-full resize-none rounded-md border border-border/40 bg-transparent p-3 text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                            />
                        </div>
                    </div>

                    {/* Runtime Block */}
                    <div className="space-y-6">
                        <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                            <span className="mr-3 text-primary">02</span> Execution
                        </h3>

                        <div className="group relative">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Entry Module Path</Label>
                            <input
                                value={formData.entry_module_path}
                                onChange={(e) => updateFormData("entry_module_path", e.target.value)}
                                className="w-full rounded-md border border-border/40 bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                            />
                        </div>

                        <div className="group relative">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Target Environment</Label>
                            <Select value={formData.runtime_target} onValueChange={(value) => updateFormData("runtime_target", value)}>
                                <SelectTrigger className="h-[38px] w-full rounded-md border border-border/40 bg-transparent px-3 text-sm shadow-none focus:ring-0 focus:ring-offset-0">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="rounded-md border-border">
                                    {RUNTIME_TARGET_OPTIONS.map((option) => (
                                        <SelectItem key={option.value} value={option.value} className="text-sm">{option.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="group relative">
                            <Label className="mb-2 block text-xs font-medium text-muted-foreground/60 transition-colors group-hover:text-foreground">Dependencies (CSV)</Label>
                            <input
                                value={formData.python_dependencies}
                                onChange={(e) => updateFormData("python_dependencies", e.target.value)}
                                className="w-full rounded-md border border-border/40 bg-transparent px-3 py-2 font-mono text-sm text-foreground outline-none shadow-none transition-colors hover:border-border focus:border-primary focus:ring-0"
                                placeholder="requests, pydantic>=2.0"
                            />
                        </div>

                        {viewMode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant" && (
                            <div className="mt-8 pt-4">
                                <Label className="mb-2 block text-xs font-medium text-destructive/80 transition-colors group-hover:text-destructive">Danger Zone</Label>
                                <div className="flex items-center gap-3 rounded-md border border-border/40 p-1">
                                    <Select value={convertTargetKind} onValueChange={(value) => setConvertTargetKind(value as ArtifactKind)}>
                                        <SelectTrigger className="h-[34px] w-full border-0 bg-transparent text-sm shadow-none focus:ring-0 focus:ring-offset-0">
                                            <SelectValue placeholder="Convert kind to..." />
                                        </SelectTrigger>
                                        <SelectContent className="rounded-md border-border">
                                            {ARTIFACT_KIND_OPTIONS.filter((option) => option.value !== formData.kind).map((option) => (
                                                <SelectItem key={option.value} value={option.value} className="text-sm">{option.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button variant="ghost" className="h-[34px] shrink-0 rounded-md px-2 text-xs font-medium text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={handleConvertKind} disabled={converting}>
                                        {converting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Convert"}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Declarations Block */}
                <div className="mt-20 space-y-12">
                    <div>
                        <div className="mb-3 flex items-end justify-between">
                            <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                                <span className="mr-3 text-primary">03</span> {contractEditorTitle(formData.kind)}
                            </h3>
                            <span className="text-[10px] text-muted-foreground">JSON</span>
                        </div>
                        <div className="h-[300px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                            <JsonEditor value={currentContractValue} onChange={updateCurrentContract} height="100%" className="h-full border-0 bg-transparent" />
                        </div>
                    </div>

                    <div>
                        <div className="mb-3 flex items-end justify-between">
                            <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                                <span className="mr-3 text-primary">04</span> Runtime Capabilities
                            </h3>
                            <span className="text-[10px] text-muted-foreground">JSON</span>
                        </div>
                        <div className="h-[300px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                            <JsonEditor value={formData.capabilities} onChange={(value) => updateFormData("capabilities", value)} height="100%" className="h-full border-0 bg-transparent" />
                        </div>
                    </div>

                    <div>
                        <div className="mb-3 flex items-end justify-between">
                            <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                                <span className="mr-3 text-primary">05</span> Configuration Schema
                            </h3>
                            <span className="text-[10px] text-muted-foreground">JSON SCHEMA</span>
                        </div>
                        <div className="h-[300px] w-full rounded-md border border-border/40 bg-muted/5 p-1 transition-colors hover:border-border/80 focus-within:border-primary">
                            <JsonEditor value={formData.config_schema} onChange={(value) => updateFormData("config_schema", value)} height="100%" className="h-full border-0 bg-transparent" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )

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
                configContent={renderConfigContent()}
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
    const artifactCodingChat = useArtifactCodingChat({
        tenantSlug: currentTenant?.slug,
        tenantId: currentTenant?.id || null,
        artifactId: selectedArtifact?.id || null,
        draftKey: artifactChatDraftKey,
        isCreateMode: viewMode === "create" || !selectedArtifact?.id,
        getDraftSnapshot: () => ({
            ...formData,
            source_files: formData.source_files.map((file) => ({ ...file })),
        }),
        onApplyDraftSnapshot: applyDraftSnapshot,
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
            {renderHeader()}
            <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden">
                {viewMode === "list" ? (
                    <div className="h-full overflow-auto" data-admin-page-scroll>{renderList()}</div>
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
        </div>
    )
}
