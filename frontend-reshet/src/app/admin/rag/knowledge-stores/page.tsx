"use client"

import { useEffect, useState, useCallback } from "react"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import {
    knowledgeStoresService,
    KnowledgeStore,
    CreateKnowledgeStoreRequest,
    credentialsService,
    IntegrationCredential,
    modelsService,
    LogicalModel,
} from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
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
    FileText,
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

import {
    KnowledgeStoreCard,
    KnowledgeStoreMetric
} from "@/components/knowledge-store-card"

function CreateKnowledgeStoreDialog({
    onCreated,
    embeddingModels,
    vectorStoreCredentials,
}: {
    onCreated: () => void
    embeddingModels: LogicalModel[]
    vectorStoreCredentials: IntegrationCredential[]
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
    const [credentialsRef, setCredentialsRef] = useState<string>("none")
    const [retrievalPolicy, setRetrievalPolicy] = useState<"semantic_only" | "hybrid">("semantic_only")
    const [chunkSize, setChunkSize] = useState(512)
    const [chunkOverlap, setChunkOverlap] = useState(50)

    const compatibleCredentials = vectorStoreCredentials.filter((cred) => {
        if (!cred.is_enabled) return false
        const provider = (cred.provider_key || "").trim().toLowerCase()
        if (backend === "pinecone") return provider === "pinecone"
        if (backend === "qdrant") return provider === "qdrant"
        return provider === "pgvector" || provider === "postgres" || provider === "postgresql"
    })
    const credentialRequired = backend === "pinecone" || backend === "qdrant"

    const handleCreate = async () => {
        if (!name || !embeddingModelId) return
        setLoading(true)
        try {
            const data: CreateKnowledgeStoreRequest = {
                name,
                description: description || undefined,
                embedding_model_id: embeddingModelId,
                backend,
                credentials_ref: credentialsRef !== "none" ? credentialsRef : undefined,
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
        setCredentialsRef("none")
        setRetrievalPolicy("semantic_only")
        setChunkSize(512)
        setChunkOverlap(50)
    }

    useEffect(() => {
        if (credentialRequired) {
            if (compatibleCredentials.length === 1) {
                setCredentialsRef(compatibleCredentials[0].id)
                return
            }
            if (credentialsRef !== "none" && compatibleCredentials.some((cred) => cred.id === credentialsRef)) {
                return
            }
            setCredentialsRef("none")
            return
        }
        if (credentialsRef !== "none" && !compatibleCredentials.some((cred) => cred.id === credentialsRef)) {
            setCredentialsRef("none")
        }
    }, [backend, credentialRequired, compatibleCredentials, credentialsRef])

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

                    <div className="space-y-2">
                        <Label className={isRTL ? "text-right block" : "text-left block"}>
                            Vector Store Credential{credentialRequired ? " *" : " (optional)"}
                        </Label>
                        <Select
                            value={credentialsRef}
                            onValueChange={setCredentialsRef}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select credential" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="none">None</SelectItem>
                                {compatibleCredentials.map((cred) => (
                                    <SelectItem key={cred.id} value={cred.id}>
                                        {cred.display_name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {credentialRequired && compatibleCredentials.length === 0 && (
                            <p className="text-xs text-destructive">
                                No enabled {backend} credential found. Add one in Settings - Integrations - Vector Stores.
                            </p>
                        )}
                    </div>

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
                    <Button
                        onClick={handleCreate}
                        disabled={!name || !embeddingModelId || loading || (credentialRequired && credentialsRef === "none")}
                    >
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
    const [vectorStoreCredentials, setVectorStoreCredentials] = useState<IntegrationCredential[]>([])
    const [embeddingModels, setEmbeddingModels] = useState<LogicalModel[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState("")
    const [editingStore, setEditingStore] = useState<KnowledgeStore | null>(null)
    const [deletingStore, setDeletingStore] = useState<KnowledgeStore | null>(null)

    const fetchData = useCallback(async () => {
        if (!currentTenant?.slug) return
        setLoading(true)
        try {
            const [storesData, modelsData, credentialsData] = await Promise.all([
                knowledgeStoresService.list(currentTenant.slug),
                modelsService.listModels("embedding"),
                credentialsService.listCredentials("vector_store"),
            ])
            setStores(storesData)
            setEmbeddingModels(modelsData.models)
            setVectorStoreCredentials(credentialsData)
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

    // Stats Calculations
    const totalDocs = stores.reduce((sum, s) => sum + s.document_count, 0)
    const totalChunks = stores.reduce((sum, s) => sum + s.chunk_count, 0)

    // Calculate Top Backend
    const backendCounts = stores.reduce((acc, store) => {
        acc[store.backend] = (acc[store.backend] || 0) + 1
        return acc
    }, {} as Record<string, number>)
    const topBackend = Object.entries(backendCounts).sort((a, b) => b[1] - a[1])[0]

    // Calculate Top Model
    const modelCounts = stores.reduce((acc, store) => {
        // Find the model object to get its name, or use the ID
        const model = embeddingModels.find(m => m.id === store.embedding_model_id)
        const modelName = model ? model.name : (store.embedding_model_id.split('/').pop() || store.embedding_model_id)

        acc[modelName] = (acc[modelName] || 0) + 1
        return acc
    }, {} as Record<string, number>)
    const topModel = Object.entries(modelCounts).sort((a, b) => b[1] - a[1])[0]


    const getModelName = (store: KnowledgeStore) => {
        const model = embeddingModels.find(m => m.id === store.embedding_model_id)
        return model ? model.name : undefined
    }


    return (
        <div className="flex flex-col h-full w-full" dir={direction}>
            <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
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
                    <CreateKnowledgeStoreDialog
                        onCreated={fetchData}
                        embeddingModels={embeddingModels}
                        vectorStoreCredentials={vectorStoreCredentials}
                    />
                </div>
            </header>

            <div className="flex-1 overflow-auto p-6">
                {loading ? (
                    <div className="space-y-4">
                        {[...Array(5)].map((_, i) => (
                            <Skeleton key={i} className="h-24 w-full rounded-xl" />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-8">
                        {/* Stats Summary - 6 Compact Blocks */}
                        <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
                            <KnowledgeStoreMetric
                                label="Active Stores"
                                value={activeStores.length}
                                subValue={`${archivedStores.length} Archived`}
                                icon={Box}
                            />
                            <KnowledgeStoreMetric
                                label="Total Documents"
                                value={totalDocs.toLocaleString()}
                                icon={Database}
                            />
                            <KnowledgeStoreMetric
                                label="Total Chunks"
                                value={totalChunks.toLocaleString()}
                                icon={Layers}
                            />
                            <KnowledgeStoreMetric
                                label="Top Backend"
                                value={topBackend ? topBackend[0] : "-"}
                                subValue={topBackend ? `${topBackend[1]} Stores` : undefined}
                                icon={Database}
                            />
                            <KnowledgeStoreMetric
                                label="Top Model"
                                value={topModel ? topModel[0] : "-"}
                                subValue={topModel ? `${topModel[1]} Stores` : undefined}
                                className="col-span-2 truncate"
                                icon={Box}
                            />
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
                            <div className="p-12 text-center border-2 border-dashed rounded-xl bg-muted/10">
                                <Box className="h-12 w-12 mx-auto text-muted-foreground mb-4 opacity-50" />
                                <h3 className="text-lg font-semibold mb-2">No Knowledge Stores</h3>
                                <p className="text-muted-foreground mb-4 max-w-sm mx-auto">
                                    Create your first knowledge store to start organizing your vectorized documents.
                                </p>
                                <CreateKnowledgeStoreDialog
                                    onCreated={fetchData}
                                    embeddingModels={embeddingModels}
                                    vectorStoreCredentials={vectorStoreCredentials}
                                />
                            </div>
                        ) : (
                            <>
                                <div className="space-y-4">
                                    {activeStores.map((store) => (
                                        <KnowledgeStoreCard
                                            key={store.id}
                                            store={store}
                                            modelName={getModelName(store)}
                                            onDelete={() => handleDelete(store)}
                                            onSettings={() => setEditingStore(store)}
                                        />
                                    ))}
                                </div>

                                {archivedStores.length > 0 && (
                                    <div className="space-y-4 pt-8 border-t">
                                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                            <Archive className="h-4 w-4" />
                                            Archived Stores ({archivedStores.length})
                                        </h3>
                                        <div className="space-y-4 opacity-75 hover:opacity-100 transition-opacity">
                                            {archivedStores.map((store) => (
                                                <KnowledgeStoreCard
                                                    key={store.id}
                                                    store={store}
                                                    modelName={getModelName(store)}
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
