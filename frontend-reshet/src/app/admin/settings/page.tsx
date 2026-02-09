"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useDirection } from "@/components/direction-provider"
import { useTenant } from "@/contexts/TenantContext"
import { useAuthStore } from "@/lib/store/useAuthStore"
import {
  credentialsService,
  orgUnitsService,
  modelsService,
  IntegrationCredential,
  IntegrationCredentialCategory,
  Tenant,
  TenantSettings,
  RetrievalPolicy,
  LogicalModel,
} from "@/services"
import { cn } from "@/lib/utils"
import { Loader2, Plus, RefreshCw, Trash2, Pencil, AlertTriangle, ShieldCheck, Building2, Search } from "lucide-react"

const CATEGORY_LABELS: Record<IntegrationCredentialCategory, { title: string; description: string }> = {
  llm_provider: {
    title: "LLM Providers",
    description: "API keys and base URLs for chat, embedding, and reranker models.",
  },
  vector_store: {
    title: "Vector Stores",
    description: "Credentials for Pinecone, Qdrant, and other vector backends.",
  },
  artifact_secret: {
    title: "Artifact Secrets",
    description: "Secrets used by custom artifacts and external integrations.",
  },
  custom: {
    title: "Custom Credentials",
    description: "Tenant-specific credentials for bespoke integrations.",
  },
}

const RETRIEVAL_POLICIES: Array<{ value: RetrievalPolicy; label: string }> = [
  { value: "semantic_only", label: "Semantic Only" },
  { value: "hybrid", label: "Hybrid" },
  { value: "keyword_only", label: "Keyword Only" },
  { value: "recency_boosted", label: "Recency Boosted" },
]

type SettingsTabKey = "profile" | "integrations" | "defaults" | "security"
const SETTINGS_TAB_ORDER: SettingsTabKey[] = ["profile", "integrations", "defaults", "security"]

function CredentialFormDialog({
  mode,
  category,
  credential,
  disabled,
  onSaved,
}: {
  mode: "create" | "edit"
  category: IntegrationCredentialCategory
  credential?: IntegrationCredential
  disabled?: boolean
  onSaved: () => void
}) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [providerKey, setProviderKey] = useState(credential?.provider_key || "")
  const [providerVariant, setProviderVariant] = useState(credential?.provider_variant || "")
  const [displayName, setDisplayName] = useState(credential?.display_name || "")
  const [credentialsText, setCredentialsText] = useState("{}")
  const [isEnabled, setIsEnabled] = useState(credential?.is_enabled ?? true)

  useEffect(() => {
    if (open) {
      setProviderKey(credential?.provider_key || "")
      setProviderVariant(credential?.provider_variant || "")
      setDisplayName(credential?.display_name || "")
      setCredentialsText("{}")
      setIsEnabled(credential?.is_enabled ?? true)
      setError(null)
    }
  }, [open, credential])

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    let parsedCredentials: Record<string, unknown> = {}
    try {
      parsedCredentials = credentialsText.trim() ? JSON.parse(credentialsText) : {}
    } catch {
      setError("Credentials must be valid JSON.")
      setLoading(false)
      return
    }

    try {
      if (mode === "create") {
        await credentialsService.createCredential({
          category,
          provider_key: providerKey,
          provider_variant: providerVariant || null,
          display_name: displayName,
          credentials: parsedCredentials,
          is_enabled: isEnabled,
        })
      } else if (credential) {
        await credentialsService.updateCredential(credential.id, {
          category,
          provider_key: providerKey,
          provider_variant: providerVariant || null,
          display_name: displayName,
          credentials: parsedCredentials,
          is_enabled: isEnabled,
        })
      }
      setOpen(false)
      onSaved()
    } catch (err) {
      console.error("Failed to save credential", err)
      setError("Failed to save credential.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {mode === "create" ? (
          <Button size="sm" disabled={disabled}>
            <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
            Add Credential
          </Button>
        ) : (
          <Button variant="ghost" size="icon" disabled={disabled}>
            <Pencil className="h-4 w-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent dir={direction}>
        <DialogHeader>
          <DialogTitle className={isRTL ? "text-right" : "text-left"}>
            {mode === "create" ? "Add Credential" : "Edit Credential"}
          </DialogTitle>
          <DialogDescription className={isRTL ? "text-right" : "text-left"}>
            Credentials are stored securely and never shown after saving.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Provider Key</Label>
            <Input value={providerKey} onChange={(e) => setProviderKey(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Provider Variant (optional)</Label>
            <Input value={providerVariant} onChange={(e) => setProviderVariant(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Display Name</Label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Credentials (JSON)</Label>
            <Textarea
              value={credentialsText}
              onChange={(e) => setCredentialsText(e.target.value)}
              className="font-mono text-xs"
              rows={6}
            />
          </div>
          <div className="flex items-center gap-3">
            <Checkbox checked={isEnabled} onCheckedChange={(v) => setIsEnabled(v === true)} />
            <Label>Enabled</Label>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={loading || !providerKey || !displayName}>
            {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function SettingsPage() {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const user = useAuthStore((state) => state.user)
  const { currentTenant, setCurrentTenant, refreshTenants } = useTenant()

  const canEdit = user?.role === "admin" || user?.org_role === "owner" || user?.org_role === "admin"

  const [activeTab, setActiveTab] = useState<SettingsTabKey>("profile")
  const [searchQuery, setSearchQuery] = useState("")
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [tenantSettings, setTenantSettings] = useState<TenantSettings>({
    default_chat_model_id: null,
    default_embedding_model_id: null,
    default_retrieval_policy: null,
  })
  const [credentials, setCredentials] = useState<IntegrationCredential[]>([])
  const [chatModels, setChatModels] = useState<LogicalModel[]>([])
  const [embeddingModels, setEmbeddingModels] = useState<LogicalModel[]>([])

  const [profileForm, setProfileForm] = useState({ name: "", slug: "", status: "active" })
  const [defaultsForm, setDefaultsForm] = useState<TenantSettings>({
    default_chat_model_id: null,
    default_embedding_model_id: null,
    default_retrieval_policy: null,
  })
  const [profileError, setProfileError] = useState<string | null>(null)
  const [defaultsError, setDefaultsError] = useState<string | null>(null)
  const [integrationsError, setIntegrationsError] = useState<string | null>(null)
  const [profileSaving, setProfileSaving] = useState(false)
  const [defaultsSaving, setDefaultsSaving] = useState(false)

  const lastTenantSlugRef = useRef<string | null>(null)
  const dirtyStateRef = useRef(false)

  const profileDirty = !!tenant && (
    profileForm.name !== tenant.name ||
    profileForm.slug !== tenant.slug ||
    profileForm.status !== tenant.status
  )

  const defaultsDirty = (
    defaultsForm.default_chat_model_id !== tenantSettings.default_chat_model_id ||
    defaultsForm.default_embedding_model_id !== tenantSettings.default_embedding_model_id ||
    defaultsForm.default_retrieval_policy !== tenantSettings.default_retrieval_policy
  )

  const hasUnsavedChanges = profileDirty || defaultsDirty
  dirtyStateRef.current = hasUnsavedChanges
  const normalizedSearch = searchQuery.trim().toLowerCase()

  const matchesSearch = useCallback((...values: Array<string | null | undefined>) => {
    if (!normalizedSearch) return true
    return values.some((value) => (value || "").toLowerCase().includes(normalizedSearch))
  }, [normalizedSearch])

  const fetchData = useCallback(async () => {
    if (!currentTenant?.slug) return
    setLoading(true)
    setFetchError(null)
    try {
      const [tenantData, settingsData, credentialsData, chatModelsData, embeddingModelsData] = await Promise.all([
        orgUnitsService.getTenant(currentTenant.slug),
        orgUnitsService.getTenantSettings(currentTenant.slug),
        credentialsService.listCredentials(),
        modelsService.listModels("chat", "active", 0, 200),
        modelsService.listModels("embedding", "active", 0, 200),
      ])

      setTenant(tenantData)
      setTenantSettings(settingsData)
      setCredentials(credentialsData)
      setChatModels(chatModelsData.models)
      setEmbeddingModels(embeddingModelsData.models)
      setProfileForm({
        name: tenantData.name,
        slug: tenantData.slug,
        status: tenantData.status,
      })
      setDefaultsForm({
        default_chat_model_id: settingsData.default_chat_model_id,
        default_embedding_model_id: settingsData.default_embedding_model_id,
        default_retrieval_policy: settingsData.default_retrieval_policy,
      })
      setProfileError(null)
      setDefaultsError(null)
      setIntegrationsError(null)
    } catch (error) {
      console.error("Failed to fetch settings hub data", error)
      setFetchError("Failed to load settings.")
    } finally {
      setLoading(false)
    }
  }, [currentTenant?.slug])

  useEffect(() => {
    if (!currentTenant?.slug) return

    if (lastTenantSlugRef.current && lastTenantSlugRef.current !== currentTenant.slug && dirtyStateRef.current) {
      window.confirm("Tenant changed. Unsaved changes were discarded.")
    }

    lastTenantSlugRef.current = currentTenant.slug
    fetchData()
  }, [currentTenant?.slug, fetchData])

  const grouped = useMemo(() => {
    return credentials.reduce<Record<IntegrationCredentialCategory, IntegrationCredential[]>>((acc, cred) => {
      acc[cred.category] = acc[cred.category] || []
      acc[cred.category].push(cred)
      return acc
    }, {
      llm_provider: [],
      vector_store: [],
      artifact_secret: [],
      custom: [],
    })
  }, [credentials])

  const integrationsFiltered = useMemo(() => {
    return (Object.keys(CATEGORY_LABELS) as IntegrationCredentialCategory[]).map((category) => {
      const categoryInfo = CATEGORY_LABELS[category]
      const items = (grouped[category] || []).filter((cred) =>
        matchesSearch(
          categoryInfo.title,
          categoryInfo.description,
          cred.display_name,
          cred.provider_key,
          cred.provider_variant || "",
          cred.credential_keys.join(" "),
          cred.is_enabled ? "enabled" : "disabled",
        )
      )
      const categoryMatch = matchesSearch(categoryInfo.title, categoryInfo.description)
      const shouldRender = categoryMatch || items.length > 0 || !normalizedSearch
      return { category, categoryInfo, items, shouldRender }
    })
  }, [grouped, matchesSearch, normalizedSearch])

  const sectionHasMatches = useMemo<Record<SettingsTabKey, boolean>>(() => ({
    profile: matchesSearch(
      "tenant profile",
      "name",
      "slug",
      "status",
      profileForm.name,
      profileForm.slug,
      profileForm.status,
      "danger zone",
      "tenant scoped routes",
    ),
    integrations: integrationsFiltered.some((entry) => entry.shouldRender),
    defaults: matchesSearch(
      "defaults",
      "default chat model",
      "default embedding model",
      "default retrieval policy",
      defaultsForm.default_chat_model_id || "",
      defaultsForm.default_embedding_model_id || "",
      defaultsForm.default_retrieval_policy || "",
      chatModels.map((m) => m.name).join(" "),
      embeddingModels.map((m) => m.name).join(" "),
    ),
    security: matchesSearch(
      "security",
      "organization",
      "roles",
      "policies",
      "org unit hierarchy",
      "member assignments",
    ),
  }), [matchesSearch, profileForm, integrationsFiltered, defaultsForm, chatModels, embeddingModels])

  useEffect(() => {
    if (!normalizedSearch) return
    if (sectionHasMatches[activeTab]) return
    const firstMatch = SETTINGS_TAB_ORDER.find((tab) => sectionHasMatches[tab])
    if (firstMatch) {
      setActiveTab(firstMatch)
    }
  }, [normalizedSearch, sectionHasMatches, activeTab])

  const handleDeleteCredential = async (credential: IntegrationCredential) => {
    if (!confirm("Delete this credential? This cannot be undone.")) return
    setIntegrationsError(null)
    try {
      await credentialsService.deleteCredential(credential.id)
      fetchData()
    } catch (error: any) {
      console.error("Failed to delete credential", error)
      const detail = error?.response?.data?.detail
      if (typeof detail === "string") {
        setIntegrationsError(detail)
      } else {
        setIntegrationsError("Failed to delete credential.")
      }
    }
  }

  const handleSaveProfile = async () => {
    if (!tenant || !currentTenant?.slug || !profileDirty) return
    setProfileSaving(true)
    setProfileError(null)
    try {
      const updated = await orgUnitsService.updateTenant(currentTenant.slug, {
        name: profileForm.name,
        slug: profileForm.slug,
        status: profileForm.status as "active" | "suspended" | "pending",
      })
      setTenant(updated)
      setProfileForm({ name: updated.name, slug: updated.slug, status: updated.status })

      if (updated.slug !== currentTenant.slug) {
        setCurrentTenant(updated)
        await refreshTenants()
      }
    } catch (error: any) {
      console.error("Failed to update tenant profile", error)
      const detail = error?.response?.data?.detail
      setProfileError(typeof detail === "string" ? detail : "Failed to update tenant profile.")
    } finally {
      setProfileSaving(false)
    }
  }

  const handleSaveDefaults = async () => {
    if (!currentTenant?.slug || !defaultsDirty) return
    setDefaultsSaving(true)
    setDefaultsError(null)
    try {
      const payload = {
        default_chat_model_id: defaultsForm.default_chat_model_id,
        default_embedding_model_id: defaultsForm.default_embedding_model_id,
        default_retrieval_policy: defaultsForm.default_retrieval_policy,
      }
      const updated = await orgUnitsService.updateTenantSettings(currentTenant.slug, payload)
      setTenantSettings(updated)
      setDefaultsForm(updated)
    } catch (error: any) {
      console.error("Failed to update tenant defaults", error)
      const detail = error?.response?.data?.detail
      setDefaultsError(typeof detail === "string" ? detail : "Failed to update tenant defaults.")
    } finally {
      setDefaultsSaving(false)
    }
  }

  const chatDefaultMissing = !!defaultsForm.default_chat_model_id && !chatModels.find((m) => m.id === defaultsForm.default_chat_model_id)
  const embeddingDefaultMissing = !!defaultsForm.default_embedding_model_id && !embeddingModels.find((m) => m.id === defaultsForm.default_embedding_model_id)

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <CustomBreadcrumb items={[{ label: "Settings", href: "/admin/settings", active: true }]} />
        <Button variant="outline" size="sm" className="h-9" onClick={fetchData}>
          <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
          Refresh
        </Button>
      </header>

      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto w-full max-w-6xl space-y-4">
        {fetchError && (
          <Card className="border-destructive/40">
            <CardContent className="py-4 text-sm text-destructive">{fetchError}</CardContent>
          </Card>
        )}

        {loading ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">Loading settings...</CardContent>
          </Card>
        ) : (
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SettingsTabKey)} className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 justify-between">
              <TabsList className="inline-flex h-auto flex-wrap gap-1 p-1">
                <TabsTrigger className="px-3 py-1.5" value="profile">Tenant Profile</TabsTrigger>
                <TabsTrigger className="px-3 py-1.5" value="integrations">Integrations</TabsTrigger>
                <TabsTrigger className="px-3 py-1.5" value="defaults">Defaults</TabsTrigger>
                <TabsTrigger className="px-3 py-1.5" value="security">Security & Organization</TabsTrigger>
              </TabsList>
              <div className="relative w-full sm:w-80">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search settings, sections, and fields..."
                  className="h-9 pl-9"
                />
              </div>
            </div>

            <TabsContent value="profile" className="space-y-4 m-0">
              {!sectionHasMatches.profile ? (
                <Card>
                  <CardContent className="py-10 text-sm text-muted-foreground">No profile matches for this search.</CardContent>
                </Card>
              ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Tenant Profile</CardTitle>
                  <CardDescription>Core tenant identity settings used across all tenant-scoped routes.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                    {matchesSearch("name", "tenant name", profileForm.name) && (
                    <div className="space-y-2 md:col-span-5">
                      <Label htmlFor="tenant-name">Name</Label>
                      <Input
                        id="tenant-name"
                        value={profileForm.name}
                        onChange={(e) => setProfileForm((prev) => ({ ...prev, name: e.target.value }))}
                        disabled={!canEdit}
                      />
                    </div>
                    )}
                    {matchesSearch("slug", "namespace", profileForm.slug) && (
                    <div className="space-y-2 md:col-span-5">
                      <Label htmlFor="tenant-slug">Slug</Label>
                      <Input
                        id="tenant-slug"
                        value={profileForm.slug}
                        onChange={(e) => setProfileForm((prev) => ({ ...prev, slug: e.target.value }))}
                        disabled={!canEdit}
                      />
                    </div>
                    )}
                    {matchesSearch("status", "active", "suspended", "pending", profileForm.status) && (
                    <div className="space-y-2 md:col-span-2">
                      <Label>Status</Label>
                      <Select
                        value={profileForm.status}
                        onValueChange={(value) => setProfileForm((prev) => ({ ...prev, status: value }))}
                        disabled={!canEdit}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="active">Active</SelectItem>
                          <SelectItem value="suspended">Suspended</SelectItem>
                          <SelectItem value="pending">Pending</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    )}
                  </div>

                  {matchesSearch("danger zone", "slug", "bookmarked urls", "tenant scoped integrations") && (
                  <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm space-y-2">
                    <div className="font-medium flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-600" />
                      Danger Zone
                    </div>
                    <p className="text-muted-foreground">
                      Changing the tenant slug can break bookmarked admin URLs and tenant-scoped integrations.
                    </p>
                  </div>
                  )}

                  {!canEdit && (
                    <p className="text-sm text-muted-foreground">You have read-only access to tenant profile settings.</p>
                  )}
                  {profileError && <p className="text-sm text-destructive">{profileError}</p>}

                  <div className={cn("flex gap-2", isRTL ? "justify-start" : "justify-end")}>
                    <Button variant="outline" onClick={fetchData} disabled={profileSaving}>Reset</Button>
                    <Button
                      onClick={handleSaveProfile}
                      disabled={!canEdit || !profileDirty || !profileForm.name.trim() || !profileForm.slug.trim() || profileSaving}
                    >
                      {profileSaving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                      Save Profile
                    </Button>
                  </div>
                </CardContent>
              </Card>
              )}
            </TabsContent>

            <TabsContent value="integrations" className="space-y-4 m-0">
              <Card>
                <CardHeader>
                  <CardTitle>Integrations</CardTitle>
                  <CardDescription>
                    Manage tenant-scoped credentials. Secret values are write-only and never returned after save.
                  </CardDescription>
                </CardHeader>
              </Card>

              {integrationsError && (
                <Card className="border-destructive/40">
                  <CardContent className="py-4 text-sm text-destructive">{integrationsError}</CardContent>
                </Card>
              )}

              {integrationsFiltered.filter((entry) => entry.shouldRender).length === 0 ? (
                <Card>
                  <CardContent className="py-10 text-sm text-muted-foreground">No integration matches for this search.</CardContent>
                </Card>
              ) : (
              integrationsFiltered.filter((entry) => entry.shouldRender).map(({ category, categoryInfo, items }) => {
                return (
                  <Card key={category}>
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="text-lg">{categoryInfo.title}</CardTitle>
                          <CardDescription>{categoryInfo.description}</CardDescription>
                        </div>
                        <CredentialFormDialog
                          mode="create"
                          category={category}
                          disabled={!canEdit}
                          onSaved={fetchData}
                        />
                      </div>
                    </CardHeader>
                    <CardContent>
                      {items.length === 0 ? (
                        <div className="text-sm text-muted-foreground">No credentials configured.</div>
                      ) : (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Display Name</TableHead>
                              <TableHead>Provider</TableHead>
                              <TableHead>Variant</TableHead>
                              <TableHead>Keys</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead className="w-[80px]"></TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {items.map((cred) => (
                              <TableRow key={cred.id}>
                                <TableCell>{cred.display_name}</TableCell>
                                <TableCell className="font-mono text-xs">{cred.provider_key}</TableCell>
                                <TableCell className="font-mono text-xs">{cred.provider_variant || "-"}</TableCell>
                                <TableCell className="text-xs text-muted-foreground">
                                  {cred.credential_keys.length ? cred.credential_keys.join(", ") : "None"}
                                </TableCell>
                                <TableCell>
                                  <Badge variant={cred.is_enabled ? "default" : "outline"}>
                                    {cred.is_enabled ? "Enabled" : "Disabled"}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  <div className="flex items-center gap-1">
                                    <CredentialFormDialog
                                      mode="edit"
                                      category={category}
                                      credential={cred}
                                      disabled={!canEdit}
                                      onSaved={fetchData}
                                    />
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      disabled={!canEdit}
                                      onClick={() => handleDeleteCredential(cred)}
                                    >
                                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      )}
                    </CardContent>
                  </Card>
                )
              }))}
            </TabsContent>

            <TabsContent value="defaults" className="space-y-4 m-0">
              {!sectionHasMatches.defaults ? (
                <Card>
                  <CardContent className="py-10 text-sm text-muted-foreground">No defaults matches for this search.</CardContent>
                </Card>
              ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Tenant Defaults</CardTitle>
                  <CardDescription>
                    Define default pointers used by tenant workflows without duplicating model-specific configuration pages.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                    {matchesSearch("default chat model", "chat", chatModels.map((model) => model.name).join(" ")) && (
                    <div className="space-y-2 md:col-span-5">
                      <Label>Default Chat Model</Label>
                      <Select
                        value={defaultsForm.default_chat_model_id || "none"}
                        onValueChange={(value) => setDefaultsForm((prev) => ({ ...prev, default_chat_model_id: value === "none" ? null : value }))}
                        disabled={!canEdit}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Select chat model" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {chatModels.map((model) => (
                            <SelectItem key={model.id} value={model.id}>{model.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    )}

                    {matchesSearch("default embedding model", "embedding", embeddingModels.map((model) => model.name).join(" ")) && (
                    <div className="space-y-2 md:col-span-5">
                      <Label>Default Embedding Model</Label>
                      <Select
                        value={defaultsForm.default_embedding_model_id || "none"}
                        onValueChange={(value) => setDefaultsForm((prev) => ({ ...prev, default_embedding_model_id: value === "none" ? null : value }))}
                        disabled={!canEdit}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Select embedding model" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {embeddingModels.map((model) => (
                            <SelectItem key={model.id} value={model.id}>{model.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    )}

                    {matchesSearch("default retrieval policy", "retrieval", RETRIEVAL_POLICIES.map((policy) => policy.label).join(" ")) && (
                    <div className="space-y-2 md:col-span-2">
                      <Label>Default Retrieval Policy</Label>
                      <Select
                        value={defaultsForm.default_retrieval_policy || "none"}
                        onValueChange={(value) => setDefaultsForm((prev) => ({ ...prev, default_retrieval_policy: value === "none" ? null : value as RetrievalPolicy }))}
                        disabled={!canEdit}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Select retrieval policy" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {RETRIEVAL_POLICIES.map((policy) => (
                            <SelectItem key={policy.value} value={policy.value}>{policy.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    )}
                  </div>

                  {(chatDefaultMissing || embeddingDefaultMissing) && (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700">
                      One or more current defaults point to missing or disabled models. Reassign and save to clear this warning.
                    </div>
                  )}

                  {!canEdit && (
                    <p className="text-sm text-muted-foreground">You have read-only access to tenant defaults.</p>
                  )}
                  {defaultsError && <p className="text-sm text-destructive">{defaultsError}</p>}

                  <div className={cn("flex gap-2", isRTL ? "justify-start" : "justify-end")}>
                    <Button variant="outline" onClick={fetchData} disabled={defaultsSaving}>Reset</Button>
                    <Button onClick={handleSaveDefaults} disabled={!canEdit || !defaultsDirty || defaultsSaving}>
                      {defaultsSaving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                      Save Defaults
                    </Button>
                  </div>
                </CardContent>
              </Card>
              )}
            </TabsContent>

            <TabsContent value="security" className="space-y-4 m-0">
              {!sectionHasMatches.security ? (
                <Card>
                  <CardContent className="py-10 text-sm text-muted-foreground">No security or organization matches for this search.</CardContent>
                </Card>
              ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Security & Organization</CardTitle>
                  <CardDescription>
                    Manage org structure and security policies in their dedicated modules. This settings page links to them without duplicating their UIs.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Building2 className="h-4 w-4" />
                        Organization
                      </CardTitle>
                      <CardDescription>Org unit hierarchy and member assignments.</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button asChild variant="outline">
                        <Link href="/admin/organization">Open Organization</Link>
                      </Button>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4" />
                        Security
                      </CardTitle>
                      <CardDescription>Roles, assignments, and workload security policies.</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Button asChild variant="outline">
                        <Link href="/admin/security">Open Security</Link>
                      </Button>
                    </CardContent>
                  </Card>
                </CardContent>
              </Card>
              )}
            </TabsContent>
          </Tabs>
        )}
        </div>
      </div>
    </div>
  )
}
