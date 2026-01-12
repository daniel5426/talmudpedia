"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import {
    modelsService,
    LogicalModel,
    ModelCapabilityType,
    ModelProviderType,
    ModelStatus,
    CreateModelRequest,
    CreateProviderRequest,
} from "@/services/agent-resources"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
    Brain,
    Plus,
    RefreshCw,
    Trash2,
    Settings,
    Loader2,
    Cpu,
    MessageSquare,
    Eye,
    Mic,
    Search as SearchIcon,
    Bot,
} from "lucide-react"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

const CAPABILITY_ICONS: Record<ModelCapabilityType, React.ElementType> = {
    chat: MessageSquare,
    embedding: Cpu,
    rerank: SearchIcon,
    vision: Eye,
    speech_to_text: Mic,
    text_to_speech: Bot,
}

const CAPABILITY_LABELS: Record<ModelCapabilityType, string> = {
    chat: "Chat / LLM",
    embedding: "Embedding",
    rerank: "Reranker",
    vision: "Vision",
    speech_to_text: "Speech to Text",
    text_to_speech: "Text to Speech",
}

const PROVIDER_LABELS: Record<ModelProviderType, string> = {
    openai: "OpenAI",
    gemini: "Google Gemini",
    anthropic: "Anthropic",
    huggingface: "HuggingFace",
    local: "Local",
    custom: "Custom",
}

function CapabilityBadge({ type }: { type: ModelCapabilityType }) {
    const Icon = CAPABILITY_ICONS[type] || Brain
    return (
        <Badge variant="outline" className="gap-1">
            <Icon className="h-3 w-3" />
            {CAPABILITY_LABELS[type] || type}
        </Badge>
    )
}

function StatusBadge({ status }: { status: ModelStatus }) {
    const variants: Record<ModelStatus, "default" | "secondary" | "destructive" | "outline"> = {
        active: "default",
        deprecated: "secondary",
        disabled: "destructive",
    }
    return <Badge variant={variants[status] || "outline"}>{status}</Badge>
}

function CreateModelDialog({ onCreated }: { onCreated: () => void }) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [form, setForm] = useState<CreateModelRequest>({
        name: "",
        slug: "",
        description: "",
        capability_type: "chat",
    })

    const handleCreate = async () => {
        if (!form.name || !form.slug) return
        setLoading(true)
        try {
            await modelsService.createModel(form)
            setOpen(false)
            setForm({ name: "", slug: "", description: "", capability_type: "chat" })
            onCreated()
        } catch (error) {
            console.error("Failed to create model", error)
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button size="sm">
                    <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                    New Model
                </Button>
            </DialogTrigger>
            <DialogContent dir={direction}>
                <DialogHeader>
                    <DialogTitle className={isRTL ? "text-right" : "text-left"}>Register Logical Model</DialogTitle>
                    <DialogDescription className={isRTL ? "text-right" : "text-left"}>
                        Define a vendor-agnostic AI model capability.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label htmlFor="name">Name</Label>
                        <Input
                            id="name"
                            placeholder="GPT-4o"
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="slug">Slug (unique identifier)</Label>
                        <Input
                            id="slug"
                            placeholder="gpt-4o"
                            value={form.slug}
                            onChange={(e) => setForm({ ...form, slug: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="capability">Capability Type</Label>
                        <Select
                            value={form.capability_type}
                            onValueChange={(v) => setForm({ ...form, capability_type: v as ModelCapabilityType })}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(CAPABILITY_LABELS).map(([key, label]) => (
                                    <SelectItem key={key} value={key}>{label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="description">Description (optional)</Label>
                        <Textarea
                            id="description"
                            placeholder="High-performance chat model..."
                            value={form.description || ""}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                    <Button onClick={handleCreate} disabled={!form.name || !form.slug || loading}>
                        {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Create
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function AddProviderDialog({ model, onAdded }: { model: LogicalModel; onAdded: () => void }) {
    const { direction } = useDirection()
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [form, setForm] = useState<CreateProviderRequest>({
        provider: "openai",
        provider_model_id: "",
        priority: 0,
    })

    const handleAdd = async () => {
        if (!form.provider_model_id) return
        setLoading(true)
        try {
            await modelsService.addProvider(model.id, form)
            setOpen(false)
            setForm({ provider: "openai", provider_model_id: "", priority: 0 })
            onAdded()
        } catch (error) {
            console.error("Failed to add provider", error)
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                    <Plus className="h-3 w-3 mr-1" />
                    Add Provider
                </Button>
            </DialogTrigger>
            <DialogContent dir={direction}>
                <DialogHeader>
                    <DialogTitle>Add Provider to {model.name}</DialogTitle>
                    <DialogDescription>
                        Configure a provider binding for runtime resolution.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Provider</Label>
                        <Select
                            value={form.provider}
                            onValueChange={(v) => setForm({ ...form, provider: v as ModelProviderType })}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(PROVIDER_LABELS).map(([key, label]) => (
                                    <SelectItem key={key} value={key}>{label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label>Provider Model ID</Label>
                        <Input
                            placeholder="gpt-4o-2024-08-06"
                            value={form.provider_model_id}
                            onChange={(e) => setForm({ ...form, provider_model_id: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Priority (lower = higher priority)</Label>
                        <Input
                            type="number"
                            value={form.priority}
                            onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value) || 0 })}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                    <Button onClick={handleAdd} disabled={!form.provider_model_id || loading}>
                        {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Add Provider
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default function ModelsPage() {
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [models, setModels] = useState<LogicalModel[]>([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState<ModelCapabilityType | "all">("all")

    const fetchModels = useCallback(async () => {
        setLoading(true)
        try {
            const capabilityType = filter === "all" ? undefined : filter
            const response = await modelsService.listModels(capabilityType)
            setModels(response.models)
        } catch (error) {
            console.error("Failed to fetch models", error)
        } finally {
            setLoading(false)
        }
    }, [filter])

    useEffect(() => {
        fetchModels()
    }, [fetchModels])

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this model?")) return
        try {
            await modelsService.deleteModel(id)
            fetchModels()
        } catch (error) {
            console.error("Failed to delete model", error)
        }
    }

    const handleRemoveProvider = async (modelId: string, providerId: string) => {
        if (!confirm("Remove this provider binding?")) return
        try {
            await modelsService.removeProvider(modelId, providerId)
            fetchModels()
        } catch (error) {
            console.error("Failed to remove provider", error)
        }
    }

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <div className="p-4 border-b shrink-0 flex items-center justify-between">
                <CustomBreadcrumb items={[
                    { label: "Dashboard", href: "/admin/dashboard" },
                    { label: "Models Registry", href: "/admin/models", active: true },
                ]} />
                <div className="flex items-center gap-2">
                    <Select value={filter} onValueChange={(v) => setFilter(v as ModelCapabilityType | "all")}>
                        <SelectTrigger className="w-[180px]">
                            <SelectValue placeholder="Filter by type" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Types</SelectItem>
                            {Object.entries(CAPABILITY_LABELS).map(([key, label]) => (
                                <SelectItem key={key} value={key}>{label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <Button variant="outline" size="sm" onClick={fetchModels}>
                        <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        Refresh
                    </Button>
                    <CreateModelDialog onCreated={fetchModels} />
                </div>
            </div>

            <div className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="space-y-4">
                        {[...Array(3)].map((_, i) => (
                            <Skeleton key={i} className="h-24 w-full" />
                        ))}
                    </div>
                ) : models.length === 0 ? (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <Brain className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                            <h3 className="text-lg font-semibold mb-2">No Models Registered</h3>
                            <p className="text-muted-foreground mb-4">
                                Register logical AI models to use in your agents.
                            </p>
                            <CreateModelDialog onCreated={fetchModels} />
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-4">
                        {models.map((model) => (
                            <Card key={model.id}>
                                <CardHeader className="pb-2">
                                    <div className={cn("flex items-start justify-between", isRTL ? "flex-row-reverse" : "flex-row")}>
                                        <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                                            <div className="flex items-center gap-2">
                                                <CardTitle className="text-lg">{model.name}</CardTitle>
                                                <StatusBadge status={model.status} />
                                            </div>
                                            <CardDescription className="font-mono text-xs">{model.slug}</CardDescription>
                                            {model.description && (
                                                <p className="text-sm text-muted-foreground mt-1">{model.description}</p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <CapabilityBadge type={model.capability_type} />
                                            <Button variant="ghost" size="icon" onClick={() => handleDelete(model.id)}>
                                                <Trash2 className="h-4 w-4 text-destructive" />
                                            </Button>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <h4 className="text-sm font-medium">Providers ({model.providers.length})</h4>
                                            <AddProviderDialog model={model} onAdded={fetchModels} />
                                        </div>
                                        {model.providers.length > 0 ? (
                                            <Table>
                                                <TableHeader>
                                                    <TableRow>
                                                        <TableHead>Provider</TableHead>
                                                        <TableHead>Model ID</TableHead>
                                                        <TableHead>Priority</TableHead>
                                                        <TableHead>Status</TableHead>
                                                        <TableHead className="w-[50px]"></TableHead>
                                                    </TableRow>
                                                </TableHeader>
                                                <TableBody>
                                                    {model.providers.map((provider) => (
                                                        <TableRow key={provider.id}>
                                                            <TableCell>
                                                                <Badge variant="secondary">
                                                                    {PROVIDER_LABELS[provider.provider] || provider.provider}
                                                                </Badge>
                                                            </TableCell>
                                                            <TableCell className="font-mono text-sm">{provider.provider_model_id}</TableCell>
                                                            <TableCell>{provider.priority}</TableCell>
                                                            <TableCell>
                                                                <Badge variant={provider.is_enabled ? "default" : "outline"}>
                                                                    {provider.is_enabled ? "Enabled" : "Disabled"}
                                                                </Badge>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="icon"
                                                                    onClick={() => handleRemoveProvider(model.id, provider.id)}
                                                                >
                                                                    <Trash2 className="h-3 w-3 text-muted-foreground" />
                                                                </Button>
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                        ) : (
                                            <p className="text-sm text-muted-foreground py-2">
                                                No providers configured. Add a provider to enable model resolution.
                                            </p>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
