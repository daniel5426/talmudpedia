"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, CustomOperator } from "@/services"
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

const DATA_TYPES = [
    { value: "none", label: "None" },
    { value: "raw_documents", label: "Raw" },
    { value: "normalized_documents", label: "Normalized" },
    { value: "enriched_documents", label: "Enriched" },
    { value: "chunks", label: "Chunks" },
    { value: "embeddings", label: "Embeddings" },
]

const DEFAULT_PYTHON_CODE = `def execute(context):
    """
    Process input data and return transformed output.
    
    Args:
        context: ExecutionContext with:
            - input_data: List of input items
            - config: Dict of configuration values
            - logger: Logger instance
    
    Returns:
        List of processed items
    """
    # Access input data
    items = context.input_data
    
    # Process each item
    result = []
    for item in items:
        # Your transformation logic here
        result.append(item)
    
    return result
`

interface OperatorFormData {
    name: string
    display_name: string
    description: string
    category: string
    input_type: string
    output_type: string
    python_code: string
    config_schema: string
}

const initialFormData: OperatorFormData = {
    name: "",
    display_name: "",
    description: "",
    category: "custom",
    input_type: "raw_documents",
    output_type: "raw_documents",
    python_code: DEFAULT_PYTHON_CODE,
    config_schema: "[]",
}

export default function OperatorsPage() {
    const { currentTenant } = useTenant()
    const router = useRouter()
    const searchParams = useSearchParams()
    const modeParam = searchParams.get("mode") as ViewMode | null
    const idParam = searchParams.get("id")

    const [viewMode, setViewMode] = useState<ViewMode>("list")
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [operators, setOperators] = useState<CustomOperator[]>([])
    const [selectedOperator, setSelectedOperator] = useState<CustomOperator | null>(null)
    const [formData, setFormData] = useState<OperatorFormData>(initialFormData)
    const [configExpanded, setConfigExpanded] = useState(true)
    const [isSlugManuallyEdited, setIsSlugManuallyEdited] = useState(false)
    const [slugError, setSlugError] = useState<string | null>(null)
    const [isSchemaMaximized, setIsSchemaMaximized] = useState(false)

    // Test Panel States
    const [isTestPanelOpen, setIsTestPanelOpen] = useState(false)
    const [isTesting, setIsTesting] = useState(false)
    const [testInput, setTestInput] = useState('[\n  {\n    "text": "Hello world",\n    "metadata": {}\n  }\n]')
    const [testConfig, setTestConfig] = useState("{\n  \n}")
    const [testResult, setTestResult] = useState<{
        success: boolean
        data: any
        error_message?: string
        execution_time_ms: number
    } | null>(null)
    const [testTab, setTestTab] = useState("input")

    // Helper to slugify a string
    const slugify = (text: string) => text.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/__+/g, "_").replace(/^_|_$/g, "")

    // Check if slug exists (excluding current operator in edit mode)
    const checkSlugCollision = (slug: string) => {
        return operators.some(
            (op) => op.name === slug && op.id !== selectedOperator?.id
        )
    }

    const fetchOperators = useCallback(async () => {
        setLoading(true)
        try {
            const data = await ragAdminService.listCustomOperators(currentTenant?.slug)
            setOperators(data)
        } catch (error) {
            console.error("Failed to fetch operators", error)
        } finally {
            setLoading(false)
        }
    }, [currentTenant?.slug])

    useEffect(() => {
        fetchOperators()
    }, [fetchOperators])

    // Handle view mode based on URL params
    useEffect(() => {
        if (loading) return

        if (modeParam === "create") {
            handleCreate()
        } else if (modeParam === "edit" && idParam) {
            const operator = operators.find(op => op.id === idParam)
            if (operator) {
                handleEdit(operator)
            } else {
                // Operator not found, go back to list
                setViewModeWithUrl("list")
            }
        } else {
            setViewMode("list")
        }
    }, [modeParam, idParam, loading, operators])

    const setViewModeWithUrl = (mode: ViewMode, id?: string) => {
        const params = new URLSearchParams()
        if (mode !== "list") params.set("mode", mode)
        if (id) params.set("id", id)
        const queryString = params.toString()
        router.push(`/admin/rag/operators${queryString ? `?${queryString}` : ""}`)
        setViewMode(mode)
    }

    const handleCreate = () => {
        setFormData(initialFormData)
        setSelectedOperator(null)
        setConfigExpanded(true)
        setIsSlugManuallyEdited(false)
        setSlugError(null)
        setViewMode("create")
    }

    const handleEdit = (operator: CustomOperator) => {
        setSelectedOperator(operator)
        setFormData({
            name: operator.name,
            display_name: operator.display_name,
            description: operator.description || "",
            category: operator.category,
            input_type: operator.input_type,
            output_type: operator.output_type,
            python_code: operator.python_code,
            config_schema: JSON.stringify(operator.config_schema || [], null, 2),
        })
        setConfigExpanded(true)
        setIsSlugManuallyEdited(true) // Existing operators have a set slug
        setSlugError(null)
        setViewMode("edit")
    }

    const handleBack = () => {
        setViewModeWithUrl("list")
        setSelectedOperator(null)
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
            try {
                configSchema = JSON.parse(formData.config_schema || "[]")
                if (!Array.isArray(configSchema)) {
                    throw new Error("Schema must be an array of objects")
                }
            } catch (e) {
                alert("Invalid Parameters JSON: " + (e instanceof Error ? e.message : "Must be a valid JSON array"))
                setSaving(false)
                return
            }

            const payload = {
                ...formData,
                config_schema: configSchema,
                name: formData.name || formData.display_name.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
            }

            if (viewMode === "create") {
                await ragAdminService.createCustomOperator(payload, currentTenant?.slug)
            } else if (selectedOperator) {
                await ragAdminService.updateCustomOperator(
                    selectedOperator.id,
                    payload,
                    currentTenant?.slug
                )
            }

            setViewModeWithUrl("list")
            fetchOperators()
        } catch (error) {
            console.error("Failed to save operator", error)
            alert("Failed to save operator")
        } finally {
            setSaving(false)
        }
    }

    const handleTestRun = async () => {
        setIsTesting(true)
        setTestTab("output")
        try {
            let inputData
            let config
            try {
                inputData = JSON.parse(testInput)
            } catch (e) {
                alert("Invalid Input JSON")
                setIsTesting(false)
                setTestTab("input")
                return
            }
            try {
                config = JSON.parse(testConfig)
            } catch (e) {
                alert("Invalid Config JSON")
                setIsTesting(false)
                setTestTab("config")
                return
            }

            const response = await ragAdminService.testCustomOperator({
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

    const handleDelete = async (operator: CustomOperator) => {
        if (!confirm(`Are you sure you want to delete "${operator.display_name}"?`)) return
        try {
            await ragAdminService.deleteCustomOperator(operator.id, currentTenant?.slug)
            fetchOperators()
        } catch (error) {
            console.error("Failed to delete operator", error)
        }
    }

    const updateFormData = (field: keyof OperatorFormData, value: string) => {
        setFormData((prev) => {
            const updated = { ...prev, [field]: value }

            // Auto-generate slug from display name (if not manually edited)
            if (field === "display_name" && !isSlugManuallyEdited) {
                updated.name = slugify(value)
            }

            // Lock slug when manually edited
            if (field === "name") {
                setIsSlugManuallyEdited(true)
            }

            // Check for collision
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

    const renderList = () => (
        <div className="space-y-6 p-4">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-lg font-semibold">Custom Operators</h2>
                    <p className="text-sm text-muted-foreground">
                        Python-based operators for custom pipeline logic
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchOperators}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={() => setViewModeWithUrl("create")}>
                        <Plus className="h-4 w-4 mr-2" />
                        New Operator
                    </Button>
                </div>
            </div>

            <Card>
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Name</TableHead>
                            <TableHead>Category</TableHead>
                            <TableHead>Input → Output</TableHead>
                            <TableHead>Version</TableHead>
                            <TableHead>Updated</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {operators.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                                    No custom operators found. Create one to get started.
                                </TableCell>
                            </TableRow>
                        ) : (
                            operators.map((op) => (
                                <TableRow key={op.id}>
                                    <TableCell className="font-medium">
                                        <div className="flex flex-col">
                                            <span>{op.display_name}</span>
                                            <span className="text-xs text-muted-foreground font-mono">{op.name}</span>
                                        </div>
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant="outline" className="capitalize">
                                            {op.category}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-sm text-muted-foreground">
                                        <span className="capitalize">{op.input_type.replace(/_/g, " ")}</span>
                                        <span className="mx-2">→</span>
                                        <span className="capitalize">{op.output_type.replace(/_/g, " ")}</span>
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant="secondary">{op.version}</Badge>
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">
                                        {new Date(op.updated_at).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-1">
                                            <Button variant="ghost" size="icon" onClick={() => setViewModeWithUrl("edit", op.id)}>
                                                <Edit className="h-4 w-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(op)}>
                                                <Trash2 className="h-4 w-4 text-destructive" />
                                            </Button>
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
            {/* Wrapper for absolute positioning */}
            <div className="flex-1 relative min-h-0">
                <div className="absolute inset-0">
                    <CodeEditor
                        value={formData.python_code}
                        onChange={(val) => updateFormData("python_code", val)}
                        height="100%"
                        className="h-full w-full border-0 rounded-none"
                    />
                </div>
            </div>

            {/* Floating Config Bubble */}
            <div className="absolute top-4 right-6 z-10">
                {configExpanded ? (
                    <Card className={cn(
                        "gap-1 py-0 shadow-lg border-border/50 bg-background/95 backdrop-blur-sm transition-all duration-300",
                        isSchemaMaximized ? "w-[500px]" : "w-90"
                    )}>
                        {/* Header */}
                        <div className="p-3 flex items-center justify-between border-b border-border/30">
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center">
                                    <Settings2 className="h-3.5 w-3.5 text-primary" />
                                </div>
                                <span className="text-xs font-semibold uppercase tracking-tight">Operator Config</span>
                            </div>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setConfigExpanded(false)}
                                className="h-6 w-6 rounded-md"
                            >
                                <X className="h-3.5 w-3.5" />
                            </Button>
                        </div>

                        {/* Tabbed Content */}
                        <Tabs
                            defaultValue="general"
                            className="w-full"
                            onValueChange={(v) => {
                                if (v === "general") setIsSchemaMaximized(false);
                            }}
                        >
                            <div className="px-3 py-2">
                                <TabsList className="grid w-full grid-cols-2">
                                    <TabsTrigger value="general">General</TabsTrigger>
                                    <TabsTrigger value="parameters">Parameters</TabsTrigger>
                                </TabsList>
                            </div>

                            <TabsContent value="general" className="p-3 space-y-3 m-0 max-h-[60vh] overflow-y-auto outline-none">
                                <div className="grid grid-cols-2 gap-2">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                            Display Name
                                        </Label>
                                        <Input
                                            value={formData.display_name}
                                            onChange={(e) => updateFormData("display_name", e.target.value)}
                                            placeholder="My Custom Operator"
                                            className="h-8 text-xs bg-muted/40 border-none"
                                        />
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                            Category
                                        </Label>
                                        <Select value={formData.category} onValueChange={(v) => updateFormData("category", v)}>
                                            <SelectTrigger className="h-8 w-full text-xs bg-muted/40 border-none">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {CATEGORIES.map((cat) => (
                                                    <SelectItem key={cat.value} value={cat.value} className="text-xs">
                                                        {cat.label}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                            Slug (ID)
                                        </Label>
                                        <div className="flex items-center gap-1">
                                            {isSlugManuallyEdited ? (
                                                <div className="flex items-center gap-1 text-[9px] text-amber-500 font-medium bg-amber-500/5 px-1 rounded">
                                                    <Lock className="h-2 w-2" />
                                                    Manual
                                                </div>
                                            ) : (
                                                <div className="flex items-center gap-1 text-[9px] text-primary font-medium bg-primary/5 px-1 rounded">
                                                    <Link className="h-2 w-2" />
                                                    Auto-linked
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <Input
                                        value={formData.name}
                                        onChange={(e) => updateFormData("name", e.target.value)}
                                        placeholder="my_custom_operator"
                                        className={cn(
                                            "h-8 text-xs font-mono bg-muted/40 border-none transition-colors",
                                            slugError && "ring-1 ring-destructive/50 bg-destructive/5"
                                        )}
                                    />
                                    {slugError && (
                                        <p className="text-[10px] text-destructive font-medium mt-1">
                                            {slugError}
                                        </p>
                                    )}
                                </div>

                                <div className="space-y-1.5">
                                    <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                        Description
                                    </Label>
                                    <Input
                                        value={formData.description}
                                        onChange={(e) => updateFormData("description", e.target.value)}
                                        placeholder="What this operator does..."
                                        className="h-8 text-xs bg-muted/40 border-none"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                            Input Type
                                        </Label>
                                        <Select
                                            value={formData.input_type}
                                            onValueChange={(v) => updateFormData("input_type", v)}
                                        >
                                            <SelectTrigger className="h-8 text-xs w-full bg-muted/40 border-none">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {DATA_TYPES.map((dt) => (
                                                    <SelectItem key={dt.value} value={dt.value} className="text-xs">
                                                        {dt.label}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-[10px] font-bold uppercase tracking-tight text-foreground/50">
                                            Output Type
                                        </Label>
                                        <Select
                                            value={formData.output_type}
                                            onValueChange={(v) => updateFormData("output_type", v)}
                                        >
                                            <SelectTrigger className="h-8 text-xs w-full bg-muted/40 border-none">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {DATA_TYPES.map((dt) => (
                                                    <SelectItem key={dt.value} value={dt.value} className="text-xs">
                                                        {dt.label}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </TabsContent>

                            <TabsContent value="parameters" className="p-0 m-0 outline-none">
                                <div className="p-3 space-y-2">
                                    <div className="flex items-center justify-between px-1">
                                        <div className="flex items-center gap-2">
                                            <p className="text-[10px] text-muted-foreground leading-tight">
                                                JSON Schema
                                            </p>
                                            {formData.config_schema && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() => {
                                                        try {
                                                            const parsed = JSON.parse(formData.config_schema)
                                                            updateFormData("config_schema", JSON.stringify(parsed, null, 2))
                                                        } catch (e) {
                                                            alert("Invalid JSON - cannot format")
                                                        }
                                                    }}
                                                    className="h-5 w-5 rounded-md hover:bg-primary/5 text-primary/60"
                                                    title="Format JSON"
                                                >
                                                    <Braces className="h-3 w-3" />
                                                </Button>
                                            )}
                                        </div>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => setIsSchemaMaximized(!isSchemaMaximized)}
                                            className="h-5 w-5 rounded-md hover:bg-primary/5"
                                            title={isSchemaMaximized ? "Minimize" : "Maximize"}
                                        >
                                            {isSchemaMaximized ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
                                        </Button>
                                    </div>
                                    <JsonEditor
                                        value={formData.config_schema}
                                        onChange={(val) => updateFormData("config_schema", val)}
                                        height={isSchemaMaximized ? "500px" : "250px"}
                                        className="border-none"
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
        <div
            className={cn(
                "border-t bg-background transition-all duration-300 ease-in-out flex flex-col",
                isTestPanelOpen ? "h-[350px]" : "h-9"
            )}
        >
            {/* Toolbar */}
            <div
                className="h-9 px-4 flex items-center justify-between border-b cursor-pointer hover:bg-muted/30 select-none"
                onClick={() => setIsTestPanelOpen(!isTestPanelOpen)}
            >
                <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-muted-foreground" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Test Console</span>
                    {testResult && (
                        <div className="flex items-center gap-2 ml-4">
                            {testResult.success ? (
                                <Badge variant="outline" className="text-[10px] h-5 bg-emerald-500/5 text-emerald-500 border-none">
                                    <CheckCircle2 className="h-3 w-3 mr-1" />
                                    Success ({testResult.execution_time_ms.toFixed(1)}ms)
                                </Badge>
                            ) : (
                                <Badge variant="outline" className="text-[10px] h-5 bg-destructive/5 text-destructive border-none">
                                    <XCircle className="h-3 w-3 mr-1" />
                                    Failed
                                </Badge>
                            )}
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {isTestPanelOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                </div>
            </div>

            {isTestPanelOpen && (
                <div className="flex-1 flex min-h-0 overflow-hidden">
                    <Tabs value={testTab} onValueChange={setTestTab} className="flex-1 flex flex-col">
                        <div className="flex items-center justify-between px-2 bg-muted/20 border-b">
                            <TabsList className="bg-transparent h-9 gap-1">
                                <TabsTrigger value="input">Input</TabsTrigger>
                                <TabsTrigger value="config">Config</TabsTrigger>
                                <TabsTrigger value="output">Output</TabsTrigger>
                            </TabsList>
                            <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs text-primary hover:text-primary hover:bg-primary/5"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleTestRun();
                                }}
                                disabled={isTesting}
                            >
                                {isTesting ? <Loader2 className="h-3 w-3 mr-2 animate-spin" /> : <Play className="h-3 w-3 mr-2 fill-current" />}
                                Run Test
                            </Button>
                        </div>

                        <div className="flex-1 min-h-0 relative">
                            <TabsContent value="input" className="absolute inset-0 m-0">
                                <CodeEditor
                                    value={testInput}
                                    onChange={setTestInput}
                                    language="json"
                                    className="h-full border-0"
                                />
                            </TabsContent>
                            <TabsContent value="config" className="absolute inset-0 m-0">
                                <CodeEditor
                                    value={testConfig}
                                    onChange={setTestConfig}
                                    language="json"
                                    className="h-full border-0"
                                />
                            </TabsContent>
                            <TabsContent value="output" className="absolute inset-0 m-0 overflow-auto p-4 font-mono text-xs">
                                {isTesting ? (
                                    <div className="flex items-center justify-center h-full text-muted-foreground gap-2">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        <span>Executing operator...</span>
                                    </div>
                                ) : testResult ? (
                                    <div className="space-y-4">
                                        {!testResult.success && testResult.error_message && (
                                            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-md text-destructive">
                                                <div className="font-bold flex items-center gap-2 mb-1">
                                                    <XCircle className="h-4 w-4" />
                                                    Execution Error
                                                </div>
                                                <pre className="whitespace-pre-wrap">{testResult.error_message}</pre>
                                            </div>
                                        )}
                                        {testResult.data && (
                                            <div>
                                                <div className="text-muted-foreground mb-2 flex items-center gap-2">
                                                    <Zap className="h-3 w-3" />
                                                    Output Data
                                                </div>
                                                <pre className="p-3 bg-muted/40 rounded-md whitespace-pre-wrap">
                                                    {JSON.stringify(testResult.data, null, 2)}
                                                </pre>
                                            </div>
                                        )}
                                        <div className="flex items-center gap-4 pt-2 text-[10px] text-muted-foreground uppercase tracking-wider font-bold">
                                            <div className="flex items-center gap-1">
                                                <Clock className="h-3 w-3" />
                                                Time: {testResult.execution_time_ms.toFixed(2)}ms
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <div className={cn("w-2 h-2 rounded-full", testResult.success ? "bg-emerald-500" : "bg-destructive")} />
                                                Status: {testResult.success ? "Success" : "Failed"}
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground italic">
                                        Run a test to see results here
                                    </div>
                                )}
                            </TabsContent>
                        </div>
                    </Tabs>
                </div>
            )}
        </div>
    )

    return (
        <div className="flex flex-col h-full w-full min-w-0 overflow-hidden">
            <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    {viewMode !== "list" && (
                        <Button variant="ghost" size="icon" onClick={handleBack} className="mr-1">
                            <ArrowLeft className="h-4 w-4" />
                        </Button>
                    )}
                    <CustomBreadcrumb
                        items={[
                            { label: "RAG Management", href: "/admin/rag" },
                            { label: "Operators", href: "/admin/rag/operators", active: viewMode === "list" },
                            ...(viewMode === "create" ? [{ label: "New Operator", active: true }] : []),
                            ...(viewMode === "edit"
                                ? [{ label: formData.display_name || "Edit Operator", active: true }]
                                : []),
                        ]}
                    />
                </div>
                {viewMode !== "list" && (
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mr-2">
                            <Code2 className="h-4 w-4" />
                            <span className="font-mono text-xs">{formData.name || "operator"}.py</span>
                        </div>
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
