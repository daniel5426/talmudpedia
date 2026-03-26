"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import {
    modelsService,
    credentialsService,
    LogicalModel,
    ModelCapabilityType,
    ModelStatus,
    CreateModelRequest,
    UpdateModelRequest,
    IntegrationCredential,
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
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
    Trash2,
    Loader2,
    Cpu,
    MessageSquare,
    Eye,
    Mic,
    Search as SearchIcon,
    Bot,
    Pencil,
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
import { Checkbox } from "@/components/ui/checkbox"
import { AddProviderDialog, EditProviderDialog, PROVIDER_LABELS } from "./components/ProviderDialogs"

const CAPABILITY_ICONS: Record<ModelCapabilityType, React.ElementType> = {
    chat: MessageSquare,
    completion: MessageSquare,
    embedding: Cpu,
    rerank: SearchIcon,
    vision: Eye,
    speech_to_text: Mic,
    text_to_speech: Bot,
    image: Eye,
    audio: Mic,
}

const CAPABILITY_LABELS: Record<ModelCapabilityType, string> = {
    chat: "Chat / LLM",
    completion: "Completion",
    embedding: "Embedding",
    rerank: "Reranker",
    vision: "Vision",
    speech_to_text: "Speech to Text",
    text_to_speech: "Text to Speech",
    image: "Image Generation",
    audio: "Audio Processing",
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
        description: "",
        capability_type: "chat",
    })

    const handleCreate = async () => {
        if (!form.name) return
        setLoading(true)
        try {
            await modelsService.createModel(form)
            setOpen(false)
            setForm({ name: "", description: "", capability_type: "chat" })
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
                        <Label htmlFor="capability">Capability Type</Label>
                        <Select
                            value={form.capability_type}
                            onValueChange={(v) => setForm({ ...form, capability_type: v as ModelCapabilityType })}
                        >
                            <SelectTrigger className="w-full">
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
                    <Button onClick={handleCreate} disabled={!form.name || loading}>
                        {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Create
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function EditModelDialog({ model, onUpdated }: { model: LogicalModel; onUpdated: () => void }) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [form, setForm] = useState<UpdateModelRequest>({
        name: model.name,
        description: model.description || "",
        status: model.status,
        is_active: model.is_active ?? true,
        is_default: model.is_default ?? false,
    })

    useEffect(() => {
        if (open) {
            setForm({
                name: model.name,
                description: model.description || "",
                status: model.status,
                is_active: model.is_active ?? true,
                is_default: model.is_default ?? false,
            })
            setError(null)
        }
    }, [open, model])

    const handleSave = async () => {
        setLoading(true)
        setError(null)
        try {
            await modelsService.updateModel(model.id, form)
            setOpen(false)
            onUpdated()
        } catch (err) {
            console.error("Failed to update model", err)
            setError("Failed to update model.")
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="ghost" size="icon" data-testid={`edit-model-${model.id}`}>
                    <Pencil className="h-4 w-4" />
                </Button>
            </DialogTrigger>
            <DialogContent dir={direction}>
                <DialogHeader>
                    <DialogTitle className={isRTL ? "text-right" : "text-left"}>Edit Model</DialogTitle>
                    <DialogDescription className={isRTL ? "text-right" : "text-left"}>
                        Update logical model settings and defaults.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label htmlFor={`name-${model.id}`}>Name</Label>
                        <Input
                            id={`name-${model.id}`}
                            value={form.name || ""}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor={`description-${model.id}`}>Description</Label>
                        <Textarea
                            id={`description-${model.id}`}
                            value={form.description || ""}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Status</Label>
                        <Select
                            value={form.status}
                            onValueChange={(v) => setForm({ ...form, status: v as ModelStatus })}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="active">Active</SelectItem>
                                <SelectItem value="deprecated">Deprecated</SelectItem>
                                <SelectItem value="disabled">Disabled</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="flex items-center gap-3">
                        <Checkbox
                            checked={!!form.is_active}
                            onCheckedChange={(v) => setForm({ ...form, is_active: v === true })}
                        />
                        <Label>Active</Label>
                    </div>
                    <div className="flex items-center gap-3">
                        <Checkbox
                            checked={!!form.is_default}
                            onCheckedChange={(v) => setForm({ ...form, is_default: v === true })}
                        />
                        <Label>Default for Capability</Label>
                    </div>
                    {error && (
                        <p className="text-sm text-destructive">{error}</p>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                    <Button onClick={handleSave} disabled={loading}>
                        {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Save Changes
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default function ModelsPage() {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [models, setModels] = useState<LogicalModel[]>([])
    const [loading, setLoading] = useState(true)
    const [credentials, setCredentials] = useState<IntegrationCredential[]>([])
    const [filter, setFilter] = useState<ModelCapabilityType | "all">("all")
    const [search, setSearch] = useState("")

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

    const fetchCredentials = useCallback(async () => {
        try {
            const response = await credentialsService.listCredentials("llm_provider")
            setCredentials(response)
        } catch (error) {
            console.error("Failed to fetch credentials", error)
        }
    }, [])

    useEffect(() => {
        fetchCredentials()
    }, [fetchCredentials])

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

    const normalizedSearch = search.trim().toLowerCase()
    const visibleModels = models.filter((model) => {
        if (!normalizedSearch) return true
        const searchableValues = [
            model.name,
            model.description || "",
            CAPABILITY_LABELS[model.capability_type] || model.capability_type,
            ...model.providers.flatMap((provider) => [
                PROVIDER_LABELS[provider.provider] || provider.provider,
                provider.provider_model_id,
            ]),
        ]
        return searchableValues.some((value) => value.toLowerCase().includes(normalizedSearch))
    })

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <AdminPageHeader>
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <CustomBreadcrumb items={[
                            { label: "Models Registry", href: "/admin/models", active: true },
                        ]} />
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-[260px]">
                        <SearchIcon className={cn("absolute top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground", isRTL ? "right-3" : "left-3")} />
                        <Input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search models..."
                            className={cn("h-9", isRTL ? "pr-9" : "pl-9")}
                        />
                    </div>
                    <Select value={filter} onValueChange={(v) => setFilter(v as ModelCapabilityType | "all")}>
                        <SelectTrigger className="h-9 w-[180px]">
                            <SelectValue placeholder="Filter by type" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Types</SelectItem>
                            {Object.entries(CAPABILITY_LABELS).map(([key, label]) => (
                                <SelectItem key={key} value={key}>{label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <CreateModelDialog onCreated={fetchModels} />
                </div>
            </AdminPageHeader>

            <div className="flex-1 overflow-auto p-4" data-admin-page-scroll>
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
                ) : visibleModels.length === 0 ? (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <SearchIcon className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
                            <h3 className="mb-2 text-lg font-semibold">No Matching Models</h3>
                            <p className="text-muted-foreground">
                                Try a different search term or clear the current filter.
                            </p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-4">
                        {visibleModels.map((model) => (
                            <Card key={model.id}>
                                <CardHeader className="pb-2">
                                    <div className={cn("flex items-start justify-between", isRTL ? "flex-row-reverse" : "flex-row")}>
                                        <div className={cn("space-y-1", isRTL ? "text-right" : "text-left")}>
                                            <div className="flex items-center gap-2">
                                                <CardTitle className="text-lg">{model.name}</CardTitle>
                                                <StatusBadge status={model.status} />
                                                {model.tenant_id === null && <Badge variant="outline">Global</Badge>}
                                            </div>
                                            {model.description && (
                                                <p className="text-sm text-muted-foreground mt-1">{model.description}</p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <CapabilityBadge type={model.capability_type} />
                                            {model.tenant_id !== null && (
                                                <>
                                                    <EditModelDialog model={model} onUpdated={fetchModels} />
                                                    <Button variant="ghost" size="icon" onClick={() => handleDelete(model.id)}>
                                                        <Trash2 className="h-4 w-4 text-destructive" />
                                                    </Button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <h4 className="text-sm font-medium">Providers ({model.providers.length})</h4>
                                            {model.tenant_id !== null ? (
                                                <AddProviderDialog model={model} credentials={credentials} onAdded={fetchModels} />
                                            ) : (
                                                <span className="text-xs text-muted-foreground">Global models are read-only.</span>
                                            )}
                                        </div>
                                        {model.providers.length > 0 ? (
                                            <Table>
                                                <TableHeader>
                                                    <TableRow>
                                                        <TableHead>Provider</TableHead>
                                                        <TableHead>Model ID</TableHead>
                                                        <TableHead>Priority</TableHead>
                                                        <TableHead>Pricing</TableHead>
                                                        <TableHead>Credentials</TableHead>
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
                                                            <TableCell className="text-xs">
                                                                {String(provider.pricing_config?.billing_mode || "unknown")}
                                                            </TableCell>
                                                            <TableCell className="text-xs">
                                                                {provider.credentials_ref
                                                                    ? credentials.find((cred) => cred.id === provider.credentials_ref)?.display_name || "Linked"
                                                                    : "Platform Default (ENV)"}
                                                            </TableCell>
                                                            <TableCell>
                                                                <Badge variant={provider.is_enabled ? "default" : "outline"}>
                                                                    {provider.is_enabled ? "Enabled" : "Disabled"}
                                                                </Badge>
                                                            </TableCell>
                                                            <TableCell>
                                                                <div className="flex items-center gap-1">
                                                                    {model.tenant_id !== null && (
                                                                        <>
                                                                            <EditProviderDialog
                                                                                model={model}
                                                                                provider={provider}
                                                                                credentials={credentials}
                                                                                onUpdated={fetchModels}
                                                                            />
                                                                            <Button
                                                                                variant="ghost"
                                                                                size="icon"
                                                                                onClick={() => handleRemoveProvider(model.id, provider.id)}
                                                                            >
                                                                                <Trash2 className="h-3 w-3 text-muted-foreground" />
                                                                            </Button>
                                                                        </>
                                                                    )}
                                                                </div>
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
