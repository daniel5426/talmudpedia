"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { artifactsService, Artifact, ArtifactScope } from "@/services/artifacts"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import {
    Plus,
    RefreshCw,
    Trash2,
    Edit,
    Loader2,
    Save,
    PanelLeft,
    Settings2,
    Play,
    Zap,
    Maximize2,
    Minimize2,
    Package,
} from "lucide-react"
import { JsonEditor } from "@/components/ui/json-editor"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"
import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"
import {
    ArtifactFormData,
    CATEGORIES,
    DATA_TYPES,
    DEFAULT_PYTHON_CODE,
    initialFormData,
    SCOPES,
} from "@/components/admin/artifacts/artifactEditorState"

type ViewMode = "list" | "create" | "edit"

export default function ArtifactsPage() {
    const { currentTenant } = useTenant()
    const router = useRouter()
    const searchParams = useSearchParams()
    const modeParam = searchParams.get("mode") as ViewMode | null
    const idParam = searchParams.get("id")

    const [viewMode, setViewMode] = useState<ViewMode>("list")
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [artifacts, setArtifacts] = useState<Artifact[]>([])
    const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
    const [formData, setFormData] = useState<ArtifactFormData>(initialFormData)
    const [isSlugManuallyEdited, setIsSlugManuallyEdited] = useState(false)
    const [slugError, setSlugError] = useState<string | null>(null)
    const [isSchemaMaximized, setIsSchemaMaximized] = useState(false)
    const [activeFilePath, setActiveFilePath] = useState("__CONFIG__")
    const [sidebarOpen, setSidebarOpen] = useState(true)

    const [promotingId, setPromotingId] = useState<string | null>(null)

    const slugify = (text: string) => text.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/__+/g, "_").replace(/^_|_$/g, "")

    const checkSlugCollision = (slug: string) => {
        return artifacts.some(
            (art) => art.name === slug && art.id !== selectedArtifact?.id
        )
    }

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
        fetchArtifacts()
    }, [fetchArtifacts])

    const setViewModeWithUrl = useCallback((mode: ViewMode, id?: string) => {
        const params = new URLSearchParams()
        if (mode !== "list") params.set("mode", mode)
        if (id) params.set("id", id)
        const queryString = params.toString()
        router.push(`/admin/artifacts${queryString ? `?${queryString}` : ""}`)
        setViewMode(mode)
    }, [router])

    const handleCreate = useCallback(() => {
        setFormData(initialFormData)
        setActiveFilePath("__CONFIG__")
        setSelectedArtifact(null)
        setIsSlugManuallyEdited(false)
        setSlugError(null)
        setViewMode("create")
    }, [])

    const handleEdit = useCallback(async (artifact: Artifact) => {
        let fullArtifact = artifact
        if (!artifact.source_files || artifact.source_files.length === 0) {
            fullArtifact = await artifactsService.get(artifact.id, currentTenant?.slug);
        }

        setSelectedArtifact(fullArtifact)
        const sourceFiles =
            fullArtifact.source_files && fullArtifact.source_files.length > 0
                ? fullArtifact.source_files
                : [{ path: "main.py", content: DEFAULT_PYTHON_CODE }]
        setFormData({
            name: fullArtifact.name,
            display_name: fullArtifact.display_name,
            description: fullArtifact.description || "",
            category: fullArtifact.category,
            scope: fullArtifact.scope,
            input_type: fullArtifact.input_type,
            output_type: fullArtifact.output_type,
            source_files: sourceFiles,
            entry_module_path: fullArtifact.entry_module_path || sourceFiles[0]?.path || "main.py",
            config_schema: JSON.stringify(fullArtifact.config_schema || [], null, 2),
            inputs: JSON.stringify(fullArtifact.inputs || [], null, 2),
            outputs: JSON.stringify(fullArtifact.outputs || [], null, 2),
            reads: (fullArtifact as any).reads || [],
            writes: (fullArtifact as any).writes || [],
        })
        setActiveFilePath("__CONFIG__")
        setIsSlugManuallyEdited(true)
        setSlugError(null)
        setViewMode("edit")
    }, [currentTenant?.slug])

    useEffect(() => {
        if (loading) return

        if (modeParam === "create") {
            handleCreate()
        } else if (modeParam === "edit" && idParam) {
            const artifact = artifacts.find(art => art.id === idParam)
            if (artifact) {
                handleEdit(artifact)
            } else {
                setViewModeWithUrl("list")
            }
        } else {
            setViewMode("list")
        }
    }, [modeParam, idParam, loading, artifacts, handleCreate, handleEdit, setViewModeWithUrl])

    const handleSave = async () => {
        if (!formData.display_name.trim()) {
            alert("Please enter a display name")
            return
        }

        if (slugError) {
            alert(slugError)
            return
        }

        setSaving(true)
        try {
            let configSchema = []
            let inputs = []
            let outputs = []
            try {
                configSchema = JSON.parse(formData.config_schema || "[]")
            } catch {
                alert("Invalid Parameters JSON")
                setSaving(false)
                return
            }
            try {
                inputs = JSON.parse(formData.inputs || "[]")
            } catch {
                alert("Invalid Inputs JSON")
                setSaving(false)
                return
            }
            try {
                outputs = JSON.parse(formData.outputs || "[]")
            } catch {
                alert("Invalid Outputs JSON")
                setSaving(false)
                return
            }

            const payload = {
                ...formData,
                config_schema: configSchema,
                inputs: inputs,
                outputs: outputs,
            }

            if (viewMode === "create") {
                await artifactsService.create(payload, currentTenant?.slug)
            } else if (selectedArtifact) {
                await artifactsService.update(selectedArtifact.id, payload, currentTenant?.slug)
            }

            setViewModeWithUrl("list")
            fetchArtifacts()
        } catch (error) {
            console.error("Failed to save artifact", error)
            alert("Failed to save artifact")
        } finally {
            setSaving(false)
        }
    }

    const handleDelete = async (artifact: Artifact) => {
        if (!confirm(`Are you sure you want to delete "${artifact.display_name}"?`)) return
        try {
            await artifactsService.delete(artifact.id, currentTenant?.slug)
            fetchArtifacts()
        } catch (error) {
            console.error("Failed to delete artifact", error)
        }
    }

    const handlePromote = async (artifact: Artifact) => {
        if (!confirm(`Promote "${artifact.display_name}" to a file-based artifact?`)) return

        setPromotingId(artifact.id)
        try {
            const result = await artifactsService.promote(artifact.id, "custom", "1.0.0", currentTenant?.slug)
            alert(`Successfully promoted to artifact: ${result.artifact_id}`)

            // If we are currently editing this artifact, go back to list
            if (selectedArtifact?.id === artifact.id) {
                setViewModeWithUrl("list")
                setSelectedArtifact(null)
            }

            fetchArtifacts()
        } catch (error) {
            console.error("Failed to promote artifact", error)
            alert("Promotion failed.")
        } finally {
            setPromotingId(null)
        }
    }

    const updateFormData = (field: keyof ArtifactFormData, value: any) => {
        setFormData((prev) => {
            const updated = { ...prev, [field]: value }
            if (field === "display_name" && !isSlugManuallyEdited) {
                updated.name = slugify(value)
            }
            if (field === "name") {
                setIsSlugManuallyEdited(true)
            }
            if (field === "name" || (field === "display_name" && !isSlugManuallyEdited)) {
                const slugToCheck = field === "name" ? value : slugify(value)
                if (slugToCheck && checkSlugCollision(slugToCheck)) {
                    setSlugError("Slug already exists")
                } else {
                    setSlugError(null)
                }
            }
            return updated
        })
    }

    const handleTestPanelOpenChange = useCallback(() => {
        // No longer toggling config view
    }, [])

    const renderHeader = () => (
        <AdminPageHeader
            contentClassName={cn(
                "px-4",
                viewMode === "list"
                    ? "h-12 items-center"
                    : "h-12 items-center",
            )}
        >
            <div className="flex min-w-0 flex-1 items-center gap-3">
                <CustomBreadcrumb
                    items={[
                        { label: "Code Artifacts", href: "/admin/artifacts", active: viewMode === "list" },
                        ...(viewMode === "create" ? [{ label: "New Artifact", active: true }] : []),
                        ...(viewMode === "edit"
                            ? [{ label: formData.display_name || "Edit Artifact", active: true }]
                            : []),
                    ]}
                />
            </div>
            {viewMode === "list" ? (
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={fetchArtifacts}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={() => setViewModeWithUrl("create")}>
                        <Plus className="h-4 w-4 mr-2" />
                        New Artifact
                    </Button>
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
                        <PanelLeft className="h-4 w-4" />
                    </Button>
                    {viewMode === "edit" && selectedArtifact && selectedArtifact.type === "draft" && (
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePromote(selectedArtifact)}
                            disabled={promotingId === selectedArtifact.id}
                            className="bg-amber-500/5 border-amber-500/20 text-amber-600 hover:bg-amber-500/10"
                        >
                            {promotingId === selectedArtifact.id ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Zap className="h-4 w-4 mr-2" />
                            )}
                            Promote
                        </Button>
                    )}
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                            const executeButton = document.getElementById("artifact-test-panel-execute")
                            executeButton?.click()
                        }}
                        className="bg-primary/5 border-primary/20 text-primary hover:bg-primary/10"
                    >
                        <Play className="h-4 w-4 mr-2 fill-current" />
                        Test
                    </Button>

                    <Button size="sm" onClick={handleSave} disabled={saving || !!slugError}>
                        {saving ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <Save className="h-4 w-4 mr-2" />
                        )}
                        Save
                    </Button>
                </div>
            )}
        </AdminPageHeader>
    )

    const renderList = () => (
        <div className="space-y-3 m-4">
            <div>
                <h2 className="text-lg font-semibold">Unified code logic</h2>
            </div>
            <div className="rounded-xl border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Artifact</TableHead>
                            <TableHead>Type / Scope</TableHead>
                            <TableHead>Category</TableHead>
                            <TableHead>Input → Output</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {artifacts.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center text-muted-foreground py-12">
                                    <div className="flex flex-col items-center gap-2">
                                        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                                            <Package className="h-6 w-6" />
                                        </div>
                                        <span>No artifacts found. Create a draft to start.</span>
                                    </div>
                                </TableCell>
                            </TableRow>
                        ) : (
                            artifacts.map((art) => (
                                <TableRow key={art.id}>
                                    <TableCell className="font-medium">
                                        <div className="flex flex-col">
                                            <span>{art.display_name}</span>
                                            <span className="text-xs text-muted-foreground font-mono">{art.name}</span>
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex flex-col gap-1">
                                            <div className="flex items-center gap-1">
                                                <Badge variant={art.type === 'draft' ? 'secondary' : art.type === 'builtin' ? 'outline' : 'default'} className="capitalize text-[9px] h-4">
                                                    {art.type}
                                                </Badge>
                                                <Badge variant="outline" className="capitalize text-[9px] h-4">
                                                    {art.scope}
                                                </Badge>
                                            </div>
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <span className="text-xs capitalize">
                                            {art.category}
                                        </span>
                                    </TableCell>
                                    <TableCell className="text-sm text-muted-foreground">
                                        <span className="capitalize">{art.input_type.replace(/_/g, " ")}</span>
                                        <span className="mx-2">→</span>
                                        <span className="capitalize">{art.output_type.replace(/_/g, " ")}</span>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-1">
                                            {art.type === 'draft' && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    title="Promote to Artifact"
                                                    onClick={() => handlePromote(art)}
                                                    disabled={promotingId === art.id}
                                                >
                                                    {promotingId === art.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4 text-amber-500" />}
                                                </Button>
                                            )}
                                            <Button variant="ghost" size="icon" onClick={() => setViewModeWithUrl("edit", art.id)}>
                                                <Edit className="h-4 w-4" />
                                            </Button>
                                            {art.type !== 'builtin' && (
                                                <Button variant="ghost" size="icon" onClick={() => handleDelete(art)}>
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            )}
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    )

    const renderConfigContent = () => (
        <div className="w-full h-full overflow-y-auto bg-background p-6 md:p-10">
            <div className="max-w-4xl mx-auto space-y-8">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-md bg-primary/10 flex items-center justify-center">
                            <Settings2 className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                            <h2 className="text-xl font-semibold tracking-tight">Artifact Configuration</h2>
                            <p className="text-sm text-muted-foreground">Adjust properties, schemas, and parameters</p>
                        </div>
                    </div>
                </div>

                <Tabs defaultValue="general" className="w-full">
                    <TabsList className="mb-6 h-10 bg-muted/50 p-1">
                        <TabsTrigger value="general" className="px-6">Properties</TabsTrigger>
                        <TabsTrigger value="io" className="px-6">I/O Schema</TabsTrigger>
                        <TabsTrigger value="parameters" className="px-6">Parameters</TabsTrigger>
                    </TabsList>

                    <TabsContent value="general" className="space-y-6 outline-none">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Display Name</Label>
                                <Input value={formData.display_name} onChange={(e) => updateFormData("display_name", e.target.value)} placeholder="e.g. Content Extractor" />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Category</Label>
                                <Select value={formData.category} onValueChange={(v) => updateFormData("category", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {CATEGORIES.map((cat) => <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <Label className="text-sm font-medium">Identifier (ID)</Label>
                                <Badge variant="outline" className="font-medium bg-background">{isSlugManuallyEdited ? 'Manual' : 'Auto-linked'}</Badge>
                            </div>
                            <Input value={formData.name} onChange={(e) => updateFormData("name", e.target.value)} className={cn("font-mono", slugError && "ring-1 ring-destructive")} />
                            {slugError && <p className="text-sm text-destructive font-medium">{slugError}</p>}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Scope</Label>
                                <Select value={formData.scope} onValueChange={(v) => updateFormData("scope", v as ArtifactScope)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {SCOPES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Version</Label>
                                <Input value={selectedArtifact?.version || "1.0.0"} disabled className="font-mono bg-muted/50" />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label className="text-sm font-medium">Description</Label>
                            <Textarea value={formData.description} onChange={(e) => updateFormData("description", e.target.value)} className="resize-none" rows={3} placeholder="Briefly describe what this artifact does..." />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Input Type</Label>
                                <Select value={formData.input_type} onValueChange={(v) => updateFormData("input_type", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {DATA_TYPES.map((dt) => <SelectItem key={dt.value} value={dt.value}>{dt.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Output Type</Label>
                                <Select value={formData.output_type} onValueChange={(v) => updateFormData("output_type", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {DATA_TYPES.map((dt) => <SelectItem key={dt.value} value={dt.value}>{dt.label}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Reads (Agent State Fields)</Label>
                                <Input
                                    placeholder="messages, transform_output, etc. (comma-separated)"
                                    value={formData.reads.join(", ")}
                                    onChange={(e) => updateFormData("reads", e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                                    className="font-mono"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Writes (Agent State Fields)</Label>
                                <Input
                                    placeholder="transform_output, etc. (comma-separated)"
                                    value={formData.writes.join(", ")}
                                    onChange={(e) => updateFormData("writes", e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                                    className="font-mono"
                                />
                            </div>
                        </div>
                    </TabsContent>

                    <TabsContent value="io" className="space-y-8 outline-none">
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label className="text-sm font-medium">Inputs Definition</Label>
                                <span className="text-xs text-muted-foreground font-mono bg-muted px-2 py-1 rounded-md">JSON</span>
                            </div>
                            <div className="border border-border/60 rounded-lg overflow-hidden ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
                                <JsonEditor
                                    value={formData.inputs}
                                    onChange={(val) => updateFormData("inputs", val)}
                                    height="280px"
                                    className="border-0 rounded-none"
                                />
                            </div>
                            <p className="text-sm text-muted-foreground">
                                Example: <code className="bg-muted px-1 py-0.5 rounded text-xs">{`[{"name": "query", "type": "string", "required": true}]`}</code>
                            </p>
                        </div>

                        <div className="h-px bg-border/40 w-full" />

                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label className="text-sm font-medium">Outputs Definition</Label>
                                <span className="text-xs text-muted-foreground font-mono bg-muted px-2 py-1 rounded-md">JSON</span>
                            </div>
                            <div className="border border-border/60 rounded-lg overflow-hidden ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
                                <JsonEditor
                                    value={formData.outputs}
                                    onChange={(val) => updateFormData("outputs", val)}
                                    height="280px"
                                    className="border-0 rounded-none"
                                />
                            </div>
                            <p className="text-sm text-muted-foreground">
                                Example: <code className="bg-muted px-1 py-0.5 rounded text-xs">{`[{"name": "result", "type": "string"}]`}</code>
                            </p>
                        </div>
                    </TabsContent>

                    <TabsContent value="parameters" className="space-y-4 outline-none">
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label className="text-sm font-medium">JSON Schema</Label>
                                <Button variant="outline" size="sm" onClick={() => setIsSchemaMaximized(!isSchemaMaximized)}>
                                    {isSchemaMaximized ? <Minimize2 className="h-4 w-4 mr-2" /> : <Maximize2 className="h-4 w-4 mr-2" />}
                                    {isSchemaMaximized ? "Shrink" : "Expand"}
                                </Button>
                            </div>
                            <div className="border border-border/60 rounded-lg overflow-hidden ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
                                <JsonEditor
                                    value={formData.config_schema}
                                    onChange={(val) => updateFormData("config_schema", val)}
                                    height={isSchemaMaximized ? "600px" : "400px"}
                                    className="border-0 rounded-none transition-all duration-300"
                                />
                            </div>
                        </div>
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    )

    const renderEditor = () => (
        <div className="relative flex-1 min-w-0 overflow-hidden flex flex-col">
            <div className="flex-1 relative min-h-0">
                <ArtifactWorkspaceEditor
                    sourceFiles={formData.source_files}
                    activeFilePath={activeFilePath}
                    entryModulePath={formData.entry_module_path}
                    onActiveFileChange={setActiveFilePath}
                    onSourceFilesChange={(files) =>
                        updateFormData(
                            "source_files",
                            files.length > 0 ? files : [{ path: "main.py", content: DEFAULT_PYTHON_CODE }]
                        )
                    }
                    sidebarOpen={sidebarOpen}
                    onSidebarOpenChange={setSidebarOpen}
                    configContent={renderConfigContent()}
                />
            </div>
        </div>
    )

    if (loading) return (
        <div className="p-8 space-y-6 w-full">
            <div className="flex items-center gap-4"><Skeleton className="h-10 w-10 rounded-full" /><div className="space-y-2"><Skeleton className="h-6 w-48" /><Skeleton className="h-4 w-64" /></div></div>
            <Card className="p-12 flex justify-center items-center"><Loader2 className="h-8 w-8 animate-spin text-primary opacity-50" /></Card>
        </div>
    )

    return (
        <div className="flex flex-col h-full w-full min-w-0 overflow-hidden">
            {renderHeader()}
            <div className="flex-1 min-h-0 min-w-0 overflow-hidden flex flex-col">
                {loading ? (
                    <div className="p-4 space-y-4">
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-[400px] w-full" />
                    </div>
                ) : viewMode === "list" ? (
                    <div className="h-full overflow-auto" data-admin-page-scroll>{renderList()}</div>
                ) : (
                    <div className="relative flex-1 min-h-0 flex flex-col overflow-hidden">
                        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                            {renderEditor()}
                        </div>
                        <ArtifactTestPanel
                            tenantSlug={currentTenant?.slug}
                            artifactId={selectedArtifact?.id}
                            sourceFiles={formData.source_files}
                            entryModulePath={formData.entry_module_path}
                            inputType={formData.input_type}
                            outputType={formData.output_type}
                            onOpenChange={handleTestPanelOpenChange}
                        />
                    </div>
                )}
            </div>
        </div>
    )
}
