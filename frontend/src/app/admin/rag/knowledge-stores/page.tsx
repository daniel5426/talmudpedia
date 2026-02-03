"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import {
    knowledgeStoresService,
    KnowledgeStore,
    CreateKnowledgeStoreRequest,
    modelsService,
    LogicalModel,
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
    Database,
    Layers,
    Plus,
    RefreshCw,
    Trash2,
    Settings,
    Box,
    Search,
    MoreHorizontal,
    Archive,
    AlertTriangle,
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

const STATUS_COLORS: Record<string, string> = {
    active: "bg-green-500/10 text-green-600 border-green-500/20",
    syncing: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    initializing: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
    error: "bg-red-500/10 text-red-600 border-red-500/20",
    archived: "bg-gray-500/10 text-gray-600 border-gray-500/20",
}

const BACKEND_ICONS: Record<string, React.ReactNode> = {
    pinecone: <Database className="h-4 w-4" />,
    pgvector: <Database className="h-4 w-4" />,
    qdrant: <Database className="h-4 w-4" />,
}

function KnowledgeStoreCard({
    store,
    onDelete,
    onSettings
}: {
    store: KnowledgeStore
    onDelete: () => void
    onSettings: () => void
}) {
    const { direction } = useDirection()
    const isRTL = direction === "rtl"

    return (
        <Card className="relative group justify-center text-center hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
                <div className={cn("flex items-start justify-between", isRTL && "flex-row-reverse")}>
                    <div className={cn("space-y-1", isRTL && "text-right")}>
                        <CardTitle className="text-lg font-semibold flex items-center gap-2">
                            <Box className="h-5 w-5 text-primary" />
                            {store.name}
                        </CardTitle>
                        {store.description && (
                            <CardDescription className="line-clamp-2">{store.description}</CardDescription>
                        )}
                    </div>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align={isRTL ? "start" : "end"}>
                            <DropdownMenuItem onClick={onSettings}>
                                <Settings className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                                Settings
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={onDelete} className="text-destructive">
                                <Trash2 className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                                Delete
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Status and Backend */}
                <div className={cn("flex items-center gap-2 flex-wrap", isRTL && "flex-row-reverse")}>
                    <Badge variant="outline" className={STATUS_COLORS[store.status]}>
                        {store.status}
                    </Badge>
                    <Badge variant="outline" className="bg-background">
                        {BACKEND_ICONS[store.backend]}
                        <span className="ml-1.5">{store.backend}</span>
                    </Badge>
                </div>

                {/* Metrics */}
                <div className={cn("grid grid-cols-2 gap-4 pt-2 border-t", isRTL && "text-right")}>
                    <div>
                        <p className="text-2xl font-bold">{store.document_count.toLocaleString()}</p>
                        <p className="text-xs text-muted-foreground">Documents</p>
                    </div>
                    <div>
                        <p className="text-2xl font-bold">{store.chunk_count.toLocaleString()}</p>
                        <p className="text-xs text-muted-foreground">Chunks</p>
                    </div>
                </div>

                {/* Config pills */}
                <div className={cn("flex flex-wrap gap-1.5 pt-2 border-t", isRTL && "flex-row-reverse")}>
                    <Badge variant="secondary" className="text-xs font-normal">
                        {store.embedding_model_id}
                    </Badge>
                    <Badge variant="secondary" className="text-xs font-normal">
                        {store.retrieval_policy.replace(/_/g, " ")}
                    </Badge>
                    {store.chunking_strategy?.strategy && (
                        <Badge variant="secondary" className="text-xs font-normal">
                            {store.chunking_strategy.strategy}
                        </Badge>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}

function CreateKnowledgeStoreDialog({
    onCreated,
    embeddingModels
}: {
    onCreated: () => void
    embeddingModels: LogicalModel[]
}) {
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)

    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [embeddingModelId, setEmbeddingModelId] = useState("")
    const [backend, setBackend] = useState<"pgvector" | "pinecone" | "qdrant">("pgvector")
    const [retrievalPolicy, setRetrievalPolicy] = useState<"semantic_only" | "hybrid">("semantic_only")
    const [chunkSize, setChunkSize] = useState(512)
    const [chunkOverlap, setChunkOverlap] = useState(50)

    const handleCreate = async () => {
        if (!name || !embeddingModelId) return
        setLoading(true)
        try {
            const data: CreateKnowledgeStoreRequest = {
                name,
                description: description || undefined,
                embedding_model_id: embeddingModelId,
                backend,
                retrieval_policy: retrievalPolicy,
                chunking_strategy: {
                    strategy: "recursive",
                    chunk_size: chunkSize,
                    chunk_overlap: chunkOverlap,
                }
            }
            await knowledgeStoresService.create(data, currentTenant?.slug)
            setOpen(false)
            resetForm()
            onCreated()
        } catch (error) {
            console.error("Failed to create knowledge store", error)
        } finally {
            setLoading(false)
        }
    }

    const resetForm = () => {
        setName("")
        setDescription("")
        setEmbeddingModelId("")
        setBackend("pgvector")
        setRetrievalPolicy("semantic_only")
        setChunkSize(512)
        setChunkOverlap(50)
    }

    return (
        <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) resetForm() }}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                    New Knowledge Store
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg" dir={direction}>
                <DialogHeader>
                    <DialogTitle className={isRTL ? "text-right" : "text-left"}>
                        Create Knowledge Store
                    </DialogTitle>
                    <DialogDescription className={isRTL ? "text-right" : "text-left"}>
                        Define a logical container for your vectorized documents.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Name */}
                    <div className="space-y-2">
                        <Label htmlFor="name" className={isRTL ? "text-right block" : "text-left block"}>
                            Name *
                        </Label>
                        <Input
                            id="name"
                            placeholder="My Knowledge Base"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className={isRTL ? "text-right" : "text-left"}
                        />
                    </div>

                    {/* Description */}
                    <div className="space-y-2">
                        <Label htmlFor="description" className={isRTL ? "text-right block" : "text-left block"}>
                            Description
                        </Label>
                        <Textarea
                            id="description"
                            placeholder="What is this knowledge store for?"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className={isRTL ? "text-right" : "text-left"}
                        />
                    </div>

                    {/* Row: Embedding Model + Storage Backend */}
                    <div className="grid grid-cols-2 gap-4">
                        {/* Embedding Model */}
                        <div className="space-y-2">
                            <Label className={isRTL ? "text-right block" : "text-left block"}>
                                Embedding Model *
                            </Label>
                            <Select value={embeddingModelId} onValueChange={setEmbeddingModelId}>
                                <SelectTrigger className="w-full">
                                    <SelectValue placeholder="Select model" />
                                </SelectTrigger>
                                <SelectContent>
                                    {embeddingModels.map((model) => (
                                        <SelectItem key={model.id} value={model.id}>
                                            {model.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Backend */}
                        <div className="space-y-2">
                            <Label className={isRTL ? "text-right block" : "text-left block"}>
                                Storage Backend
                            </Label>
                            <Select value={backend} onValueChange={(v) => setBackend(v as typeof backend)}>
                                <SelectTrigger className="w-full">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="pgvector">PGVector (Postgres)</SelectItem>
                                    <SelectItem value="pinecone">Pinecone</SelectItem>
                                    <SelectItem value="qdrant">Qdrant</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <p className="text-xs text-muted-foreground -mt-2">
                        The embedding model is immutable after creation.
                    </p>

                    {/* Row: Retrieval Policy + Chunking Settings */}
                    <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label className={isRTL ? "text-right block" : "text-left block"}>
                                Retrieval Policy
                            </Label>
                            <Select value={retrievalPolicy} onValueChange={(v) => setRetrievalPolicy(v as typeof retrievalPolicy)}>
                                <SelectTrigger className="w-full">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="semantic_only">Semantic Only</SelectItem>
                                    <SelectItem value="hybrid">Hybrid</SelectItem>
                                    <SelectItem value="recency_boosted">Recency Boosted</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label className={isRTL ? "text-right block" : "text-left block"}>
                                Chunk Size
                            </Label>
                            <Input
                                type="number"
                                value={chunkSize}
                                onChange={(e) => setChunkSize(Number(e.target.value))}
                                min={100}
                                max={2000}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className={isRTL ? "text-right block" : "text-left block"}>
                                Chunk Overlap
                            </Label>
                            <Input
                                type="number"
                                value={chunkOverlap}
                                onChange={(e) => setChunkOverlap(Number(e.target.value))}
                                min={0}
                                max={500}
                            />
                        </div>
                    </div>
                </div>

                <DialogFooter className="sm:justify-center justify-center">
                    <Button variant="outline" onClick={() => setOpen(false)}>
                        Cancel
                    </Button>
                    <Button onClick={handleCreate} disabled={!name || !embeddingModelId || loading}>
                        {loading ? "Creating..." : "Create Store"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function EditKnowledgeStoreDialog({
    store,
    open,
    onOpenChange,
    onUpdated
}: {
    store: KnowledgeStore | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onUpdated: () => void
}) {
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [loading, setLoading] = useState(false)

    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [retrievalPolicy, setRetrievalPolicy] = useState<"semantic_only" | "hybrid" | "recency_boosted">("semantic_only")

    useEffect(() => {
        if (store) {
            setName(store.name)
            setDescription(store.description || "")
            setRetrievalPolicy(store.retrieval_policy as any)
        }
    }, [store])

    const handleUpdate = async () => {
        if (!store || !name) return
        setLoading(true)
        try {
            await knowledgeStoresService.update(store.id, {
                name,
                description: description || undefined,
                retrieval_policy: retrievalPolicy
            }, currentTenant?.slug)
            onOpenChange(false)
            onUpdated()
        } catch (error) {
            console.error("Failed to update knowledge store", error)
        } finally {
            setLoading(false)
        }
    }

    if (!store) return null

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg" dir={direction}>
                <DialogHeader>
                    <DialogTitle className={isRTL ? "text-right" : "text-left"}>
                        Edit Knowledge Store
                    </DialogTitle>
                    <DialogDescription className={isRTL ? "text-right" : "text-left"}>
                        Update configuration for {store.name}.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Name */}
                    <div className="space-y-2">
                        <Label htmlFor="edit-name" className={isRTL ? "text-right block" : "text-left block"}>
                            Name *
                        </Label>
                        <Input
                            id="edit-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className={isRTL ? "text-right" : "text-left"}
                        />
                    </div>

                    {/* Description */}
                    <div className="space-y-2">
                        <Label htmlFor="edit-description" className={isRTL ? "text-right block" : "text-left block"}>
                            Description
                        </Label>
                        <Textarea
                            id="edit-description"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className={isRTL ? "text-right" : "text-left"}
                        />
                    </div>

                    {/* Retrieval Policy */}
                    <div className="space-y-2">
                        <Label className={isRTL ? "text-right block" : "text-left block"}>
                            Retrieval Policy
                        </Label>
                        <Select value={retrievalPolicy} onValueChange={(v) => setRetrievalPolicy(v as any)}>
                            <SelectTrigger className="w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="semantic_only">Semantic Only</SelectItem>
                                <SelectItem value="hybrid">Hybrid (Semantic + Keyword)</SelectItem>
                                <SelectItem value="recency_boosted">Recency Boosted</SelectItem>
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                            Changing policy affects how results are ranked at query time.
                        </p>
                    </div>

                    {/* Immutable Fields Display */}
                    <div className="grid grid-cols-2 gap-4 pt-2 border-t mt-4">
                        <div>
                            <p className="text-xs font-medium text-muted-foreground">Embedding Model</p>
                            <p className="text-sm">{store.embedding_model_id}</p>
                        </div>
                        <div>
                            <p className="text-xs font-medium text-muted-foreground">Backend</p>
                            <p className="text-sm capitalize">{store.backend}</p>
                        </div>
                    </div>
                </div>

                <DialogFooter className="sm:justify-center justify-center">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button onClick={handleUpdate} disabled={!name || loading}>
                        {loading ? "Saving..." : "Save Changes"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function DeleteKnowledgeStoreDialog({
    store,
    open,
    onOpenChange,
    onDeleted
}: {
    store: KnowledgeStore | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onDeleted: () => void
}) {
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"
    const [loading, setLoading] = useState(false)

    const handleDelete = async () => {
        if (!store) return
        setLoading(true)
        try {
            await knowledgeStoresService.delete(store.id, currentTenant?.slug)
            onOpenChange(false)
            onDeleted()
        } catch (error) {
            console.error("Failed to delete knowledge store", error)
        } finally {
            setLoading(false)
        }
    }

    if (!store) return null

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md text-center justify-center" dir={direction}>
                <DialogHeader>
                    <div className={cn("mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-2", isRTL ? "ml-auto mr-0" : "")}>
                        <AlertTriangle className="h-6 w-6 text-destructive" />
                    </div>
                    <DialogTitle className={cn("text-xl text-center")}>
                        Delete Knowledge Store
                    </DialogTitle>
                    <DialogDescription className={"text-center"}>
                        Are you sure you want to delete <strong>{store.name}</strong>?
                        <br />
                        This will archive all data and cannot be undone.
                    </DialogDescription>
                </DialogHeader>

                <DialogFooter className="mt-4 sm:justify-center justify-center">
                    <Button variant="destructive" onClick={handleDelete} disabled={loading}>
                        {loading ? "Deleting..." : "Delete Knowledge Store"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default function KnowledgeStoresPage() {
    const { currentTenant } = useTenant()
    const { direction } = useDirection()
    const isRTL = direction === "rtl"

    const [stores, setStores] = useState<KnowledgeStore[]>([])
    const [embeddingModels, setEmbeddingModels] = useState<LogicalModel[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState("")
    const [editingStore, setEditingStore] = useState<KnowledgeStore | null>(null)
    const [deletingStore, setDeletingStore] = useState<KnowledgeStore | null>(null)

    const fetchData = useCallback(async () => {
        if (!currentTenant?.slug) return
        setLoading(true)
        try {
            const [storesData, modelsData] = await Promise.all([
                knowledgeStoresService.list(currentTenant.slug),
                modelsService.listModels("embedding"),
            ])
            setStores(storesData)
            setEmbeddingModels(modelsData.models)
        } catch (error) {
            console.error("Failed to fetch knowledge stores", error)
        } finally {
            setLoading(false)
        }
    }, [currentTenant])

    useEffect(() => {
        fetchData()
    }, [fetchData])

    const handleDelete = (store: KnowledgeStore) => {
        setDeletingStore(store)
    }

    const filteredStores = stores.filter(store =>
        store.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        store.description?.toLowerCase().includes(searchQuery.toLowerCase())
    )

    const activeStores = filteredStores.filter(s => s.status !== "archived")
    const archivedStores = filteredStores.filter(s => s.status === "archived")

    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
                <div className="flex items-center gap-3">
                    <CustomBreadcrumb items={[
                        { label: "RAG Management", href: "/admin/rag" },
                        { label: "Knowledge Stores", href: "/admin/rag/knowledge-stores", active: true },
                    ]} />
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={fetchData}>
                        <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
                        Refresh
                    </Button>
                    <CreateKnowledgeStoreDialog onCreated={fetchData} embeddingModels={embeddingModels} />
                </div>
            </header>

            <div className="flex-1 overflow-auto p-6">
                {loading ? (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {[...Array(6)].map((_, i) => (
                            <Skeleton key={i} className="h-64 w-full" />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-6">
                        {/* Stats Summary */}
                        <div className="grid gap-4 md:grid-cols-3">
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Box className="h-4 w-4 text-muted-foreground" />
                                        Active Stores
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">{activeStores.length}</div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Layers className="h-4 w-4 text-muted-foreground" />
                                        Total Chunks
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">
                                        {stores.reduce((sum, s) => sum + s.chunk_count, 0).toLocaleString()}
                                    </div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Database className="h-4 w-4 text-muted-foreground" />
                                        Total Documents
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold">
                                        {stores.reduce((sum, s) => sum + s.document_count, 0).toLocaleString()}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Search */}
                        <div className="relative max-w-md">
                            <Search className={cn(
                                "absolute top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground",
                                isRTL ? "right-3" : "left-3"
                            )} />
                            <Input
                                placeholder="Search knowledge stores..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className={cn("pl-9", isRTL && "pr-9 pl-3 text-right")}
                            />
                        </div>

                        {/* Store Grid */}
                        {activeStores.length === 0 && archivedStores.length === 0 ? (
                            <Card className="p-12 text-center">
                                <Box className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                                <h3 className="text-lg font-semibold mb-2">No Knowledge Stores</h3>
                                <p className="text-muted-foreground mb-4">
                                    Create your first knowledge store to start organizing your vectorized documents.
                                </p>
                                <CreateKnowledgeStoreDialog onCreated={fetchData} embeddingModels={embeddingModels} />
                            </Card>
                        ) : (
                            <>
                                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                    {activeStores.map((store) => (
                                        <KnowledgeStoreCard
                                            key={store.id}
                                            store={store}
                                            onDelete={() => handleDelete(store)}
                                            onSettings={() => setEditingStore(store)}
                                        />
                                    ))}
                                </div>

                                {archivedStores.length > 0 && (
                                    <div className="space-y-4 pt-6 border-t">
                                        <h3 className="text-lg font-medium flex items-center gap-2">
                                            <Archive className="h-5 w-5" />
                                            Archived ({archivedStores.length})
                                        </h3>
                                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 opacity-60">
                                            {archivedStores.map((store) => (
                                                <KnowledgeStoreCard
                                                    key={store.id}
                                                    store={store}
                                                    onDelete={() => handleDelete(store)}
                                                    onSettings={() => setEditingStore(store)}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}
            </div>

            <EditKnowledgeStoreDialog
                store={editingStore}
                open={!!editingStore}
                onOpenChange={(open) => !open && setEditingStore(null)}
                onUpdated={fetchData}
            />

            <DeleteKnowledgeStoreDialog
                store={deletingStore}
                open={!!deletingStore}
                onOpenChange={(open) => !open && setDeletingStore(null)}
                onDeleted={fetchData}
            />
        </div>
    )
}
