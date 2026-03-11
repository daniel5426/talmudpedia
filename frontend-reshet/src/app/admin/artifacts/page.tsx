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
import { JsonEditor } from "@/components/ui/json-editor"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { ArtifactTestPanel } from "@/components/admin/artifacts/ArtifactTestPanel"
import { ArtifactWorkspaceEditor } from "@/components/admin/artifacts/ArtifactWorkspaceEditor"
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
  contractEditorDescription,
  contractEditorTitle,
  formDataFromArtifact,
  kindLabel,
  slugify,
  tryParseObject,
} from "@/components/admin/artifacts/artifactPageUtils"
import {
  ArrowRightLeft,
  Bot,
  Database,
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
  const [kindSelectionPending, setKindSelectionPending] = useState(false)
  const [convertTargetKind, setConvertTargetKind] = useState<ArtifactKind>("rag_operator")
  const [isSlugManuallyEdited, setIsSlugManuallyEdited] = useState(false)
  const [slugError, setSlugError] = useState<string | null>(null)
  const [activeFilePath, setActiveFilePath] = useState("__CONFIG__")
  const [sidebarOpen, setSidebarOpen] = useState(true)

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

  const handleCreate = useCallback(() => {
    setSelectedArtifact(null)
    setFormData(initialFormData)
    setActiveFilePath("__CONFIG__")
    setIsSlugManuallyEdited(false)
    setSlugError(null)
    setKindSelectionPending(true)
    setViewMode("create")
  }, [])

  const handleChooseKind = useCallback((kind: ArtifactKind) => {
    const next = createFormDataForKind(kind)
    setFormData(next)
    setSelectedArtifact(null)
    setActiveFilePath("__CONFIG__")
    setIsSlugManuallyEdited(false)
    setSlugError(null)
    setConvertTargetKind(kind === "agent_node" ? "rag_operator" : "agent_node")
    setKindSelectionPending(false)
    setViewMode("create")
  }, [])

  const handleEdit = useCallback(async (artifact: Artifact) => {
    const fullArtifact = await artifactsService.get(artifact.id, currentTenant?.slug)
    setSelectedArtifact(fullArtifact)
    setFormData(formDataFromArtifact(fullArtifact))
    setActiveFilePath("__CONFIG__")
    setIsSlugManuallyEdited(true)
    setSlugError(null)
    setKindSelectionPending(false)
    setConvertTargetKind(fullArtifact.kind === "agent_node" ? "rag_operator" : "agent_node")
    setViewMode("edit")
  }, [currentTenant?.slug])

  useEffect(() => {
    if (loading) return
    if (modeParam === "create") {
      handleCreate()
      return
    }
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
  }, [artifacts, handleCreate, handleEdit, idParam, loading, modeParam, setViewModeWithUrl])

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

  const handleSave = async () => {
    if (kindSelectionPending) return
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
        setKindSelectionPending(false)
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
    <AdminPageHeader contentClassName="px-4 h-12 items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <CustomBreadcrumb
          items={[
            { label: "Artifacts", href: "/admin/artifacts", active: viewMode === "list" },
            ...(viewMode === "create" ? [{ label: kindSelectionPending ? "Choose Kind" : "New Artifact", active: true }] : []),
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
          <Button size="sm" onClick={() => setViewModeWithUrl("create")}>
            <Plus className="mr-2 h-4 w-4" />
            New Artifact
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          {!kindSelectionPending && (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSidebarOpen((prev) => !prev)}
                className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                title={sidebarOpen ? "Hide file explorer" : "Show file explorer"}
              >
                <PanelLeft className="h-4 w-4" />
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
            </>
          )}
        </div>
      )}
    </AdminPageHeader>
  )

  const renderKindChooser = () => (
    <div className="grid gap-4 p-4 md:grid-cols-3">
      {ARTIFACT_KIND_OPTIONS.map((option) => {
        const Icon = kindIcon(option.value)
        return (
          <Card
            key={option.value}
            className="cursor-pointer border-border/60 p-6 transition hover:border-primary/40 hover:bg-primary/5"
            onClick={() => handleChooseKind(option.value)}
          >
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Icon className="h-6 w-6" />
            </div>
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">{option.label}</h3>
              <p className="text-sm text-muted-foreground">{option.description}</p>
            </div>
          </Card>
        )
      })}
    </div>
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
    <div className="h-full w-full overflow-y-auto bg-background p-6 md:p-10">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="border-b border-border/40 pb-4">
          <h2 className="text-xl font-semibold tracking-tight">Artifact Configuration</h2>
          <p className="text-sm text-muted-foreground">Author runtime, interface, and domain-specific contract in one place.</p>
        </div>

        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="mb-6 h-10 bg-muted/50 p-1">
            <TabsTrigger value="overview" className="px-4">Overview</TabsTrigger>
            <TabsTrigger value="runtime" className="px-4">Runtime</TabsTrigger>
            <TabsTrigger value="contract" className="px-4">Contract</TabsTrigger>
            <TabsTrigger value="capabilities" className="px-4">Capabilities</TabsTrigger>
            <TabsTrigger value="schema" className="px-4">Config Schema</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6 outline-none">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Display Name</Label>
                <Input value={formData.display_name} onChange={(e) => updateFormData("display_name", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Artifact Kind</Label>
                <div className="flex h-10 items-center rounded-md border px-3">
                  <Badge variant="outline">{kindLabel(formData.kind)}</Badge>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Slug</Label>
              <Input
                value={formData.slug}
                onChange={(e) => updateFormData("slug", e.target.value)}
                className={cn("font-mono", slugError && "ring-1 ring-destructive")}
              />
              {slugError && <p className="text-sm text-destructive">{slugError}</p>}
            </div>

            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                value={formData.description}
                onChange={(e) => updateFormData("description", e.target.value)}
                rows={3}
                className="resize-none"
              />
            </div>

            {viewMode === "edit" && selectedArtifact?.type === "draft" && selectedArtifact.owner_type === "tenant" && (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <ArrowRightLeft className="h-4 w-4 text-amber-600" />
                  Convert Kind
                </div>
                <p className="mb-4 text-sm text-muted-foreground">
                  Draft-only conversion clears incompatible contract fields and revalidates against the target kind.
                </p>
                <div className="flex flex-col gap-3 md:flex-row">
                  <Select value={convertTargetKind} onValueChange={(value) => setConvertTargetKind(value as ArtifactKind)}>
                    <SelectTrigger className="md:w-72">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ARTIFACT_KIND_OPTIONS.filter((option) => option.value !== formData.kind).map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button variant="outline" onClick={handleConvertKind} disabled={converting}>
                    {converting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowRightLeft className="mr-2 h-4 w-4" />}
                    Convert Kind
                  </Button>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="runtime" className="space-y-6 outline-none">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Entrypoint</Label>
                <Input value={formData.entry_module_path} onChange={(e) => updateFormData("entry_module_path", e.target.value)} className="font-mono" />
              </div>
              <div className="space-y-2">
                <Label>Runtime Target</Label>
                <Select value={formData.runtime_target} onValueChange={(value) => updateFormData("runtime_target", value)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RUNTIME_TARGET_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Python Dependencies</Label>
              <Input
                value={formData.python_dependencies}
                onChange={(e) => updateFormData("python_dependencies", e.target.value)}
                placeholder="requests, pydantic, ..."
                className="font-mono"
              />
            </div>
          </TabsContent>

          <TabsContent value="contract" className="space-y-3 outline-none">
            <div>
              <Label>{contractEditorTitle(formData.kind)}</Label>
              <p className="mt-1 text-sm text-muted-foreground">{contractEditorDescription(formData.kind)}</p>
            </div>
            <div className="overflow-hidden rounded-lg border border-border/60">
              <JsonEditor value={currentContractValue} onChange={updateCurrentContract} height="420px" className="border-0 rounded-none" />
            </div>
          </TabsContent>

          <TabsContent value="capabilities" className="space-y-3 outline-none">
            <div>
              <Label>Runtime Capabilities</Label>
              <p className="mt-1 text-sm text-muted-foreground">Declare side effects, network access, storage, and secret usage explicitly.</p>
            </div>
            <div className="overflow-hidden rounded-lg border border-border/60">
              <JsonEditor value={formData.capabilities} onChange={(value) => updateFormData("capabilities", value)} height="360px" className="border-0 rounded-none" />
            </div>
          </TabsContent>

          <TabsContent value="schema" className="space-y-3 outline-none">
            <div>
              <Label>Config Schema</Label>
              <p className="mt-1 text-sm text-muted-foreground">This is the shared runtime configuration schema for the artifact itself.</p>
            </div>
            <div className="overflow-hidden rounded-lg border border-border/60">
              <JsonEditor value={formData.config_schema} onChange={(value) => updateFormData("config_schema", value)} height="420px" className="border-0 rounded-none" />
            </div>
          </TabsContent>
        </Tabs>
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
        ) : kindSelectionPending ? (
          renderKindChooser()
        ) : (
          <div className="relative w-full flex min-h-0 flex-1 flex-col overflow-hidden">
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
            />
          </div>
        )}
      </div>
    </div>
  )
}
