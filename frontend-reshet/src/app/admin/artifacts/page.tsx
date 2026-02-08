"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { artifactsService, Artifact, ArtifactType, ArtifactScope, ArtifactTestResponse } from "@/services/artifacts"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
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
    ArrowLeft,
    Code2,
    Settings2,
    X,
    Lock,
    Link,
    Play,
    Terminal,
    ChevronUp,
    ChevronDown,
    Zap,
    CheckCircle2,
    XCircle,
    Clock,
    Maximize2,
    Minimize2,
    Braces,
    FileCode,
    Database,
    Package,
} from "lucide-react"
import { CodeEditor } from "@/components/ui/code-editor"
import { JsonEditor } from "@/components/ui/json-editor"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

type ViewMode = "list" | "create" | "edit"

const CATEGORIES = [
    { value: "source", label: "Source" },
    { value: "normalization", label: "Normalization" },
    { value: "enrichment", label: "Enrichment" },
    { value: "chunking", label: "Chunking" },
    { value: "transform", label: "Transform" },
    { value: "custom", label: "Custom" },
]

const SCOPES = [
    { value: "rag", label: "RAG" },
    { value: "agent", label: "Agent" },
    { value: "both", label: "Both" },
]

const DATA_TYPES = [
    { value: "none", label: "None" },
    { value: "raw_documents", label: "Raw" },
    { value: "normalized_documents", label: "Normalized" },
    { value: "enriched_documents", label: "Enriched" },
    { value: "chunks", label: "Chunks" },
    { value: "embeddings", label: "Embeddings" },
    { value: "any", label: "Any (Agent)" },
]

const DEFAULT_PYTHON_CODE = `def execute(context):
    """
    Process input data and return transformed output.
    
    Args:
        context: ArtifactContext with:
            - input_data: List of input items
            - config: Dict of configuration values
            - logger: Logger instance
    
    Returns:
        Processed data (matches output_type)
    """
    # Access input data
    items = context.input_data
    
    # Your transformation logic here
    return items
`

interface ArtifactFormData {
    name: string
    display_name: string
    description: string
    category: string
    scope: ArtifactScope
    input_type: string
    output_type: string
    python_code: string
    config_schema: string
    inputs: string
    outputs: string
    reads: string[]
    writes: string[]
}

const initialFormData: ArtifactFormData = {
    name: "",
    display_name: "",
    description: "",
    category: "custom",
    scope: "rag",
    input_type: "raw_documents",
    output_type: "raw_documents",
    python_code: DEFAULT_PYTHON_CODE,
    config_schema: "[]",
    inputs: "[]",
    outputs: "[]",
    reads: [],
    writes: [],
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
    const [artifacts, setArtifacts] = useState<Artifact[]>([])
    const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
    const [formData, setFormData] = useState<ArtifactFormData>(initialFormData)
    const [configExpanded, setConfigExpanded] = useState(true)
    const [isSlugManuallyEdited, setIsSlugManuallyEdited] = useState(false)
    const [slugError, setSlugError] = useState<string | null>(null)
    const [isSchemaMaximized, setIsSchemaMaximized] = useState(false)

    // Test Panel States
    const [isTestPanelOpen, setIsTestPanelOpen] = useState(false)
    const [isTesting, setIsTesting] = useState(false)
    const [testInput, setTestInput] = useState('[\n  {\n    "text": "Hello world",\n    "metadata": {}\n  }\n]')
    const [testConfig, setTestConfig] = useState("{\n  \n}")
    const [testResult, setTestResult] = useState<ArtifactTestResponse | null>(null)
    const [testTab, setTestTab] = useState("input")
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
    }, [modeParam, idParam, loading, artifacts])

    const setViewModeWithUrl = (mode: ViewMode, id?: string) => {
        const params = new URLSearchParams()
        if (mode !== "list") params.set("mode", mode)
        if (id) params.set("id", id)
        const queryString = params.toString()
        router.push(`/admin/artifacts${queryString ? `?${queryString}` : ""}`)
        setViewMode(mode)
    }

    const handleCreate = () => {
        setFormData(initialFormData)
        setSelectedArtifact(null)
        setConfigExpanded(true)
        setIsSlugManuallyEdited(false)
        setSlugError(null)
        setViewMode("create")
    }

    const handleEdit = async (artifact: Artifact) => {
        // Fetch full details (including code if not loaded)
        let fullArtifact = artifact;
        if (!artifact.python_code) {
            fullArtifact = await artifactsService.get(artifact.id, currentTenant?.slug);
        }

        setSelectedArtifact(fullArtifact)
        setFormData({
            name: fullArtifact.name,
            display_name: fullArtifact.display_name,
            description: fullArtifact.description || "",
            category: fullArtifact.category,
            scope: fullArtifact.scope,
            input_type: fullArtifact.input_type,
            output_type: fullArtifact.output_type,
            python_code: fullArtifact.python_code || DEFAULT_PYTHON_CODE,
            config_schema: JSON.stringify(fullArtifact.config_schema || [], null, 2),
            inputs: JSON.stringify(fullArtifact.inputs || [], null, 2),
            outputs: JSON.stringify(fullArtifact.outputs || [], null, 2),
            reads: (fullArtifact as any).reads || [],
            writes: (fullArtifact as any).writes || [],
        })
        setConfigExpanded(true)
        setIsSlugManuallyEdited(true)
        setSlugError(null)
        setViewMode("edit")
    }

    const handleBack = () => {
        setViewModeWithUrl("list")
        setSelectedArtifact(null)
    }

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
            } catch (e) {
                alert("Invalid Parameters JSON")
                setSaving(false)
                return
            }
            try {
                inputs = JSON.parse(formData.inputs || "[]")
            } catch (e) {
                alert("Invalid Inputs JSON")
                setSaving(false)
                return
            }
            try {
                outputs = JSON.parse(formData.outputs || "[]")
            } catch (e) {
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

    const handleTestRun = async () => {
        setIsTesting(true)
        setTestTab("output")
        try {
            let inputData, config
            try { inputData = JSON.parse(testInput) } catch (e) { alert("Invalid Input JSON"); setIsTesting(false); setTestTab("input"); return; }
            try { config = JSON.parse(testConfig) } catch (e) { alert("Invalid Config JSON"); setIsTesting(false); setTestTab("config"); return; }

            const response = await artifactsService.test({
                artifact_id: selectedArtifact?.id,
                python_code: formData.python_code,
                input_data: inputData,
                config: config,
                input_type: formData.input_type,
                output_type: formData.output_type,
            }, currentTenant?.slug)

            setTestResult(response)
        } catch (error) {
            console.error("Test execution failed", error)
            setTestResult({
                success: false,
                data: null,
                error_message: error instanceof Error ? error.message : "Unknown error",
                execution_time_ms: 0,
            })
        } finally {
            setIsTesting(false)
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

    const renderHeader = () => (
        <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
            <div className="flex items-center gap-3">
                <CustomBreadcrumb
                    items={[
                        { label: "Admin", href: "/admin/dashboard" },
                        { label: "Code Artifacts", href: "/admin/artifacts", active: viewMode === "list" },
                        ...(viewMode === "create" ? [{ label: "New Artifact", active: true }] : []),
                        ...(viewMode === "edit"
                            ? [{ label: formData.display_name || "Edit Artifact", active: true }]
                            : []),
                    ]}
                />
            </div>
            {viewMode !== "list" && (
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground mr-2">
                        <Code2 className="h-4 w-4" />
                        <span className="font-mono text-xs">{formData.name || "artifact"}.py</span>
                    </div>
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
                        onClick={handleTestRun}
                        disabled={isTesting}
                        className="bg-primary/5 border-primary/20 text-primary hover:bg-primary/10"
                    >
                        {isTesting ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <Play className="h-4 w-4 mr-2 fill-current" />
                        )}
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
        </header>
    )

    const getTypeIcon = (type: ArtifactType) => {
        switch (type) {
            case "draft": return <Database className="h-3 w-3" />;
            case "promoted": return <FileCode className="h-3 w-3" />;
            case "builtin": return <Package className="h-3 w-3" />;
        }
    }

    const renderList = () => (
        <div className="space-y-6 p-4">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-lg font-semibold">Code Artifacts</h2>
                    <p className="text-sm text-muted-foreground">
                        Unified code logic for RAG pipelines, Agents, and Tools
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchArtifacts}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={() => setViewModeWithUrl("create")}>
                        <Plus className="h-4 w-4 mr-2" />
                        New Artifact
                    </Button>
                </div>
            </div>

            <Card>
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
            </Card>
        </div>
    )

    const renderEditor = () => (
        <div className="relative flex-1 min-w-0 overflow-hidden flex flex-col">
            <div className="flex-1 relative min-h-0">
                <CodeEditor
                    value={formData.python_code}
                    onChange={(val) => updateFormData("python_code", val)}
                    height="100%"
                    className="h-full w-full border-0 rounded-none"
                />
            </div>

            {/* Floating Config Bubble */}
            <div className="absolute top-4 right-6 z-10">
                {configExpanded ? (
                    <Card className={cn(
                        "gap-1 py-0 shadow-2xl border-border/50 bg-background/95 backdrop-blur-sm transition-all duration-300",
                        isSchemaMaximized ? "w-[500px]" : "w-96"
                    )}>
                        <div className="p-3 flex items-center justify-between border-b border-border/30">
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center">
                                    <Settings2 className="h-3.5 w-3.5 text-primary" />
                                </div>
                                <span className="text-xs font-semibold uppercase tracking-tight">Artifact Config</span>
                            </div>
                            <Button variant="ghost" size="icon" onClick={() => setConfigExpanded(false)} className="h-6 w-6 rounded-md">
                                <X className="h-3.5 w-3.5" />
                            </Button>
                        </div>

                        <Tabs defaultValue="general" className="w-full">
                            <div className="px-3 py-2">
                                <TabsList className="grid w-full grid-cols-3">
                                    <TabsTrigger value="general" className="text-xs">Properties</TabsTrigger>
                                    <TabsTrigger value="io" className="text-xs">I/O Schema</TabsTrigger>
                                    <TabsTrigger value="parameters" className="text-xs">Parameters</TabsTrigger>
                                </TabsList>
                            </div>

                            <TabsContent value="general" className="p-4 space-y-4 m-0 max-h-[65vh] overflow-y-auto outline-none">
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Display Name</Label>
                                        <Input value={formData.display_name} onChange={(e) => updateFormData("display_name", e.target.value)} className="h-8 text-xs" />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Category</Label>
                                        <Select value={formData.category} onValueChange={(v) => updateFormData("category", v)}>
                                            <SelectTrigger className="w-full h-8 text-xs"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {CATEGORIES.map((cat) => <SelectItem key={cat.value} value={cat.value} className="text-xs">{cat.label}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Identifier (ID)</Label>
                                        <Badge variant="outline" className="h-4 text-[9px] font-medium">{isSlugManuallyEdited ? 'Manual' : 'Auto-linked'}</Badge>
                                    </div>
                                    <Input value={formData.name} onChange={(e) => updateFormData("name", e.target.value)} className={cn("h-8 text-xs font-mono", slugError && "ring-1 ring-destructive/50")} />
                                    {slugError && <p className="text-[10px] text-destructive font-medium mt-1">{slugError}</p>}
                                </div>

                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Scope</Label>
                                        <Select value={formData.scope} onValueChange={(v) => updateFormData("scope", v as ArtifactScope)}>
                                            <SelectTrigger className="w-full h-8 text-xs"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {SCOPES.map((s) => <SelectItem key={s.value} value={s.value} className="text-xs">{s.label}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Version</Label>
                                        <Input value={selectedArtifact?.version || "1.0.0"} disabled className="h-8 text-xs font-mono" />
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <Label className="text-[10px] font-bold uppercase text-foreground/50">Description</Label>
                                    <Textarea value={formData.description} onChange={(e) => updateFormData("description", e.target.value)} className="text-xs resize-none" rows={2} />
                                </div>

                                <div className="grid grid-cols-2 gap-3">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Input Type</Label>
                                        <Select value={formData.input_type} onValueChange={(v) => updateFormData("input_type", v)}>
                                            <SelectTrigger className="w-full h-8 text-xs"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {DATA_TYPES.map((dt) => <SelectItem key={dt.value} value={dt.value} className="text-xs">{dt.label}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase text-foreground/50">Output Type</Label>
                                        <Select value={formData.output_type} onValueChange={(v) => updateFormData("output_type", v)}>
                                            <SelectTrigger className="w-full h-8 text-xs"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {DATA_TYPES.map((dt) => <SelectItem key={dt.value} value={dt.value} className="text-xs">{dt.label}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <Label className="text-[10px] font-bold uppercase text-foreground/50">Reads (Agent State Fields)</Label>
                                    <Input
                                        placeholder="messages, transform_output, etc. (comma-separated)"
                                        value={formData.reads.join(", ")}
                                        onChange={(e) => updateFormData("reads", e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                                        className="h-8 text-xs font-mono"
                                    />
                                </div>

                                <div className="space-y-1.5">
                                    <Label className="text-[10px] font-bold uppercase text-foreground/50">Writes (Agent State Fields)</Label>
                                    <Input
                                        placeholder="transform_output, etc. (comma-separated)"
                                        value={formData.writes.join(", ")}
                                        onChange={(e) => updateFormData("writes", e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                                        className="h-8 text-xs font-mono"
                                    />
                                </div>
                            </TabsContent>

                            <TabsContent value="io" className="p-0 m-0 outline-none">
                                <div className="p-4 space-y-4 max-h-[65vh] overflow-y-auto">
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <span className="text-[10px] font-bold uppercase text-foreground/50">Inputs Definition (JSON)</span>
                                            <Badge variant="outline" className="h-4 text-[8px]">Field Mapping</Badge>
                                        </div>
                                        <JsonEditor
                                            value={formData.inputs}
                                            onChange={(val) => updateFormData("inputs", val)}
                                            height="180px"
                                            className="border-border/30 rounded-md overflow-hidden"
                                        />
                                        <p className="text-[9px] text-muted-foreground italic">
                                            {'Example: [{"name": "query", "type": "string", "required": true}]'}
                                        </p>
                                    </div>

                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <span className="text-[10px] font-bold uppercase text-foreground/50">Outputs Definition (JSON)</span>
                                        </div>
                                        <JsonEditor
                                            value={formData.outputs}
                                            onChange={(val) => updateFormData("outputs", val)}
                                            height="180px"
                                            className="border-border/30 rounded-md overflow-hidden"
                                        />
                                        <p className="text-[9px] text-muted-foreground italic">
                                            {'Example: [{"name": "result", "type": "string"}]'}
                                        </p>
                                    </div>
                                </div>
                            </TabsContent>

                            <TabsContent value="parameters" className="p-0 m-0 outline-none">
                                <div className="p-4 space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] font-bold uppercase text-foreground/50">JSON Schema (Config)</span>
                                        <Button variant="ghost" size="icon" onClick={() => setIsSchemaMaximized(!isSchemaMaximized)} className="h-6 w-6">
                                            {isSchemaMaximized ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
                                        </Button>
                                    </div>
                                    <JsonEditor
                                        value={formData.config_schema}
                                        onChange={(val) => updateFormData("config_schema", val)}
                                        height={isSchemaMaximized ? "500px" : "250px"}
                                        className="border-border/30 rounded-md overflow-hidden"
                                    />
                                </div>
                            </TabsContent>
                        </Tabs>
                    </Card>
                ) : (
                    /* Collapsed bubble - small circle */
                    <Button
                        variant="outline"
                        size="icon"
                        onClick={() => setConfigExpanded(true)}
                        className="h-10 w-10 rounded-full shadow-lg bg-background/95 backdrop-blur-sm border-border/50 hover:scale-105 transition-transform"
                    >
                        <Settings2 className="h-4 w-4" />
                    </Button>
                )}
            </div>
        </div>
    )

    const renderTestPanel = () => (
        <div className={cn("border-t bg-background flex flex-col transition-all duration-300", isTestPanelOpen ? "h-[400px]" : "h-10")}>
            <div className="h-10 px-4 flex items-center justify-between border-b bg-muted/20 cursor-pointer hover:bg-muted/40 transition-colors" onClick={() => setIsTestPanelOpen(!isTestPanelOpen)}>
                <div className="flex items-center gap-3">
                    <Terminal className="h-4 w-4 text-primary" />
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Test Runtime</span>
                    {testResult && (
                        <Badge variant={testResult.success ? "secondary" : "destructive"} className="h-5 text-[10px] gap-1 px-2 border-none">
                            {testResult.success ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                            {testResult.success ? `Ready (${testResult.execution_time_ms.toFixed(1)}ms)` : "Error"}
                        </Badge>
                    )}
                </div>
                {isTestPanelOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </div>

            {isTestPanelOpen && (
                <div className="flex-1 flex overflow-hidden">
                    <Tabs value={testTab} onValueChange={setTestTab} className="flex-1 flex flex-col">
                        <div className="flex items-center justify-between px-2 py-1 bg-muted/10 border-b">
                            <TabsList className="bg-transparent h-8 gap-0.5">
                                <TabsTrigger value="input" className="text-[11px] h-7 px-3">Input Data (JSON)</TabsTrigger>
                                <TabsTrigger value="config" className="text-[11px] h-7 px-3">Runtime Config</TabsTrigger>
                                <TabsTrigger value="output" className="text-[11px] h-7 px-3">Trace Output</TabsTrigger>
                            </TabsList>
                            <Button size="sm" onClick={(e) => { e.stopPropagation(); handleTestRun(); }} disabled={isTesting} className="h-7 px-4 text-xs">
                                {isTesting ? <Loader2 className="h-3 w-3 animate-spin mr-2" /> : <Play className="h-3.3 w-3.5 fill-current mr-2" />}
                                Execute
                            </Button>
                        </div>
                        <div className="flex-1 min-h-0 relative">
                            <TabsContent value="input" className="absolute inset-0 m-0">
                                <CodeEditor value={testInput} onChange={setTestInput} language="json" className="h-full" />
                            </TabsContent>
                            <TabsContent value="config" className="absolute inset-0 m-0">
                                <CodeEditor value={testConfig} onChange={setTestConfig} language="json" className="h-full" />
                            </TabsContent>
                            <TabsContent value="output" className="absolute inset-0 m-0 p-4 font-mono text-sm overflow-auto transition-colors">
                                {isTesting ? (
                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
                                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                                        <span className="animate-pulse">Synthesizing execution environment...</span>
                                    </div>
                                ) : testResult ? (
                                    <div className="space-y-4">
                                        {testResult.success ? (
                                            <pre className="text-emerald-400 whitespace-pre-wrap">{JSON.stringify(testResult.data, null, 2)}</pre>
                                        ) : (
                                            <div className="text-rose-400">
                                                <p className="font-bold underline mb-2">Execution Failed:</p>
                                                <pre className="whitespace-pre-wrap">{testResult.error_message}</pre>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground">
                                        <span>No execution trace yet. Click "Execute" to start session.</span>
                                    </div>
                                )}
                            </TabsContent>
                        </div>
                    </Tabs>
                </div>
            )}
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
                    <div className="h-full overflow-auto">{renderList()}</div>
                ) : (
                    <>
                        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                            {renderEditor()}
                        </div>
                        {renderTestPanel()}
                    </>
                )}
            </div>
        </div>
    )
}
