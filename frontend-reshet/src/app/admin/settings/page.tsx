"use client"

import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
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
import {
  AlertTriangle,
  Building2,
  ChevronRight,
  KeyRound,
  Loader2,
  PlugZap,
  ShieldCheck,
  Sliders,
  User,
} from "lucide-react"
import { CredentialFormDialog } from "./components/CredentialFormDialog"
import { CredentialDeleteDialog } from "./components/CredentialDeleteDialog"
import McpSettingsSection from "./mcp/page"

const CATEGORY_LABELS: Record<IntegrationCredentialCategory, { title: string; description: string }> = {
  llm_provider: {
    title: "LLM Providers",
    description: "API keys and base URLs for chat, embedding, and reranker models.",
  },
  vector_store: {
    title: "Vector Stores",
    description: "Credentials for Pinecone, Qdrant, and other vector backends.",
  },
  tool_provider: {
    title: "Tools",
    description: "Credentials for web-search tool providers like Serper, Tavily, and Exa.",
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
type SettingsSection = "profile" | "integrations" | "mcp_servers" | "security"

const NAV_ITEMS: Array<{ key: SettingsSection; label: string; icon: any }> = [
  { key: "profile", label: "General", icon: User },
  { key: "integrations", label: "Credentials", icon: KeyRound },
  { key: "mcp_servers", label: "MCP Servers", icon: PlugZap },
  { key: "security", label: "Security", icon: ShieldCheck },
]

function parseSection(value: string | null): SettingsSection {
  return NAV_ITEMS.some((item) => item.key === value) ? (value as SettingsSection) : "profile"
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      <p className="text-xs text-muted-foreground/70 mt-0.5">{description}</p>
    </div>
  )
}



function LoadingSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-56" />
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex gap-6 py-4 border-b border-border/40">
          <Skeleton className="h-4 w-28 shrink-0" />
          <Skeleton className="h-9 flex-1 max-w-md" />
        </div>
      ))}
    </div>
  )
}

export default function SettingsPage() {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const user = useAuthStore((state) => state.user)
  const { currentTenant, setCurrentTenant, refreshTenants } = useTenant()

  const canEdit = user?.role === "admin" || user?.org_role === "owner" || user?.org_role === "admin"

  const [activeSection, setActiveSection] = useState<SettingsSection>(() => parseSection(searchParams.get("tab")))
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

  const profileDirty =
    !!tenant &&
    (profileForm.name !== tenant.name || profileForm.slug !== tenant.slug || profileForm.status !== tenant.status)

  const defaultsDirty =
    defaultsForm.default_chat_model_id !== tenantSettings.default_chat_model_id ||
    defaultsForm.default_embedding_model_id !== tenantSettings.default_embedding_model_id ||
    defaultsForm.default_retrieval_policy !== tenantSettings.default_retrieval_policy

  const hasUnsavedChanges = profileDirty || defaultsDirty
  dirtyStateRef.current = hasUnsavedChanges

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

  useEffect(() => {
    const nextSection = parseSection(searchParams.get("tab"))
    setActiveSection((currentSection) => (currentSection === nextSection ? currentSection : nextSection))
  }, [searchParams])

  const handleSectionChange = useCallback(
    (section: SettingsSection) => {
      setActiveSection(section)
      const params = new URLSearchParams(searchParams.toString())
      if (section === "profile") {
        params.delete("tab")
      } else {
        params.set("tab", section)
      }
      const nextQuery = params.toString()
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false })
    },
    [pathname, router, searchParams]
  )

  const grouped = useMemo(() => {
    return credentials.reduce<Record<IntegrationCredentialCategory, IntegrationCredential[]>>(
      (acc, cred) => {
        acc[cred.category] = acc[cred.category] || []
        acc[cred.category].push(cred)
        return acc
      },
      {
        llm_provider: [],
        vector_store: [],
        tool_provider: [],
        custom: [],
      }
    )
  }, [credentials])

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

  const chatDefaultMissing =
    !!defaultsForm.default_chat_model_id && !chatModels.find((m) => m.id === defaultsForm.default_chat_model_id)
  const embeddingDefaultMissing =
    !!defaultsForm.default_embedding_model_id &&
    !embeddingModels.find((m) => m.id === defaultsForm.default_embedding_model_id)

  function renderProfile() {
    return (
      <div className="space-y-6">
        <SectionHeader title="General Settings" description="Core identity and platform defaults." />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Identity Column */}
          <div className="space-y-5">
            <h3 className="text-sm font-semibold text-foreground border-b border-border/40 pb-2">Identity</h3>
            
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Tenant Name</Label>
                <Input
                  value={profileForm.name}
                  onChange={(e) => setProfileForm((prev) => ({ ...prev, name: e.target.value }))}
                  disabled={!canEdit}
                  className="h-9 w-full"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Status</Label>
                <Select
                  value={profileForm.status}
                  onValueChange={(value) => setProfileForm((prev) => ({ ...prev, status: value }))}
                  disabled={!canEdit}
                >
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="suspended">Suspended</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Defaults Column */}
          <div className="space-y-5">
            <h3 className="text-sm font-semibold text-foreground border-b border-border/40 pb-2">Defaults</h3>
            
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Default Chat Model</Label>
                <Select
                  value={defaultsForm.default_chat_model_id || "none"}
                  onValueChange={(value) => setDefaultsForm((prev) => ({ ...prev, default_chat_model_id: value === "none" ? null : value }))}
                  disabled={!canEdit}
                >
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue placeholder="Select chat model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {chatModels.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Default Embedding Model</Label>
                <Select
                  value={defaultsForm.default_embedding_model_id || "none"}
                  onValueChange={(value) =>
                    setDefaultsForm((prev) => ({ ...prev, default_embedding_model_id: value === "none" ? null : value }))
                  }
                  disabled={!canEdit}
                >
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue placeholder="Select embedding model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {embeddingModels.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Retrieval Policy</Label>
                <Select
                  value={defaultsForm.default_retrieval_policy || "none"}
                  onValueChange={(value) =>
                    setDefaultsForm((prev) => ({
                      ...prev,
                      default_retrieval_policy: value === "none" ? null : (value as RetrievalPolicy),
                    }))
                  }
                  disabled={!canEdit}
                >
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue placeholder="Select policy" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {RETRIEVAL_POLICIES.map((policy) => (
                      <SelectItem key={policy.value} value={policy.value}>
                        {policy.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </div>

        {/* Warnings & Errors */}
        {(chatDefaultMissing || embeddingDefaultMissing) && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 mt-2 flex items-start gap-2 max-w-2xl">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>One or more defaults point to missing or disabled models.</span>
          </div>
        )}

        {!canEdit && (
          <p className="text-xs text-muted-foreground/60 mt-2">Read-only access. Contact an admin to make changes.</p>
        )}
        
        {(profileError || defaultsError) && (
          <div className="space-y-1 mt-2">
            {profileError && <p className="text-sm text-destructive">{profileError}</p>}
            {defaultsError && <p className="text-sm text-destructive">{defaultsError}</p>}
          </div>
        )}

        <div className={cn("flex gap-2 pt-6 border-t border-border/40 mt-6", isRTL ? "justify-start" : "justify-end")}>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={profileSaving || defaultsSaving}>
            Reset
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              if (profileDirty) await handleSaveProfile();
              if (defaultsDirty) await handleSaveDefaults();
            }}
            disabled={!canEdit || (!profileDirty && !defaultsDirty) || !profileForm.name.trim() || profileSaving || defaultsSaving}
          >
            {(profileSaving || defaultsSaving) && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
            Save Changes
          </Button>
        </div>
      </div>
    )
  }

  function renderIntegrations() {
    return (
      <div>
        <SectionHeader
          title="Credentials"
          description="Manage tenant-scoped credentials. Secret values are write-only."
        />

        {integrationsError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive mb-4">
            {integrationsError}
          </div>
        )}

        <div className="space-y-6">
          {(Object.keys(CATEGORY_LABELS) as IntegrationCredentialCategory[]).map((category) => {
            const categoryInfo = CATEGORY_LABELS[category]
            const items = grouped[category] || []
            return (
              <div key={category} className="rounded-lg border border-border/50">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border/40">
                  <div>
                    <h3 className="text-sm font-medium">{categoryInfo.title}</h3>
                    <p className="text-xs text-muted-foreground/60 mt-0.5">{categoryInfo.description}</p>
                  </div>
                  <CredentialFormDialog mode="create" category={category} disabled={!canEdit} onSaved={fetchData} />
                </div>

                {items.length === 0 ? (
                  <div className="px-4 py-6 text-center">
                    <p className="text-xs text-muted-foreground/50">No credentials configured.</p>
                  </div>
                ) : (
                  <div className="divide-y divide-border/30">
                    {items.map((cred) => (
                      <div key={cred.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium truncate font-mono">{cred.provider_key}</span>
                            {cred.is_default && (
                              <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-700">
                                Default
                              </span>
                            )}
                            <span className="flex items-center gap-1 shrink-0">
                              <span className={cn("h-1.5 w-1.5 rounded-full", cred.is_enabled ? "bg-emerald-500" : "bg-zinc-400")} />
                              <span className="text-xs text-muted-foreground/60">{cred.is_enabled ? "Active" : "Disabled"}</span>
                            </span>
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-muted-foreground/50 font-mono">{cred.display_name}</span>
                            {cred.credential_keys.length > 0 && (
                              <>
                                <span className="text-muted-foreground/30">·</span>
                                <span className="text-xs text-muted-foreground/40">
                                  {cred.credential_keys.length} key{cred.credential_keys.length !== 1 ? "s" : ""}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <CredentialFormDialog
                            mode="edit"
                            category={category}
                            credential={cred}
                            disabled={!canEdit}
                            onSaved={fetchData}
                          />
                          <CredentialDeleteDialog
                            credential={cred}
                            disabled={!canEdit}
                            onDeleted={fetchData}
                            onError={(message) => setIntegrationsError(message || null)}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  function renderSecurity() {
    return (
      <div>
        <SectionHeader
          title="Security & Organization"
          description="Manage org structure and security policies in their dedicated modules."
        />

        <div className="space-y-2">
          <Link
            href="/admin/organization"
            className="group flex items-center gap-3 rounded-lg border border-border/50 px-4 py-3.5 hover:bg-muted/30 transition-colors"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70 group-hover:border-border group-hover:bg-muted/50 transition-colors">
              <Building2 className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium text-foreground">Organization</span>
              <p className="text-xs text-muted-foreground/60 mt-0.5">Org unit hierarchy and member assignments.</p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
          </Link>

          <Link
            href="/admin/security"
            className="group flex items-center gap-3 rounded-lg border border-border/50 px-4 py-3.5 hover:bg-muted/30 transition-colors"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70 group-hover:border-border group-hover:bg-muted/50 transition-colors">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium text-foreground">Security & Roles</span>
              <p className="text-xs text-muted-foreground/60 mt-0.5">Roles, assignments, API keys, and resource policy governance.</p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
          </Link>
        </div>
      </div>
    )
  }
  const SECTION_RENDERERS: Record<SettingsSection, () => React.ReactNode> = {
    profile: renderProfile,
    integrations: renderIntegrations,
    mcp_servers: () => <McpSettingsSection />,
    security: renderSecurity,
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <AdminPageHeader>
        <CustomBreadcrumb items={[{ label: "Settings", href: "/admin/settings", active: true }]} />
        {hasUnsavedChanges && <span className="text-xs text-amber-600 font-medium">Unsaved changes</span>}
      </AdminPageHeader>

      <div className="flex-1 flex overflow-hidden">
        <nav className="w-48 shrink-0 p-3 overflow-y-auto hidden sm:block">
          <div className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = activeSection === item.key
              return (
                <button
                  key={item.key}
                  onClick={() => handleSectionChange(item.key)}
                  className={cn(
                    "flex items-center gap-2.5 w-full rounded-md px-2.5 py-1.5 text-sm transition-colors text-left",
                    isActive ? "bg-muted/60 text-foreground font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {item.label}
                </button>
              )
            })}
          </div>
        </nav>

        <div className="sm:hidden shrink-0 border-b border-border/40 px-4 py-2 flex gap-1 overflow-x-auto">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => handleSectionChange(item.key)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs whitespace-nowrap transition-colors",
                activeSection === item.key ? "bg-muted/60 text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <main className="flex-1 overflow-y-auto" data-admin-page-scroll>
          <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
            {loading ? (
              <LoadingSkeleton />
            ) : fetchError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {fetchError}
              </div>
            ) : (
              SECTION_RENDERERS[activeSection]()
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
