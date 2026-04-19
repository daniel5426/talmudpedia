"use client"

import { useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import {
  KeyRound,
  LayoutList,
  PlugZap,
  ShieldCheck,
  User,
  Wallet,
} from "lucide-react"

import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { useDirection } from "@/components/direction-provider"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/lib/store/useAuthStore"
import {
  credentialsService,
  IntegrationCredential,
  LogicalModel,
  modelsService,
  settingsOrgService,
  settingsProfileService,
  SettingsOrganization,
  SettingsProfile,
} from "@/services"
import { formatHttpErrorMessage } from "@/services/http"
import { CredentialDeleteDialog } from "./components/CredentialDeleteDialog"
import { CredentialFormDialog } from "./components/CredentialFormDialog"
import {
  ApiKeysSection,
  AuditLogsSection,
  LimitsSection,
  PeoplePermissionsSection,
  ProjectsSection,
} from "./components/GovernanceSections"
import McpSettingsPage from "./mcp/page"

type SettingsSection =
  | "organization"
  | "profile"
  | "people_permissions"
  | "projects"
  | "api_keys"
  | "limits"
  | "audit_logs"
  | "integrations"
  | "mcp_servers"

const NAV_ITEMS: Array<{ key: SettingsSection; label: string; icon: any }> = [
  { key: "organization", label: "Organization", icon: LayoutList },
  { key: "profile", label: "Profile", icon: User },
  { key: "people_permissions", label: "People & Permissions", icon: ShieldCheck },
  { key: "projects", label: "Projects", icon: LayoutList },
  { key: "api_keys", label: "API Keys", icon: KeyRound },
  { key: "limits", label: "Limits", icon: Wallet },
  { key: "audit_logs", label: "Audit Logs", icon: ShieldCheck },
  { key: "integrations", label: "Integrations", icon: KeyRound },
  { key: "mcp_servers", label: "MCP Servers", icon: PlugZap },
]

const CATEGORY_LABELS: Record<string, { title: string; description: string }> = {
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
    description: "Organization-specific credentials for bespoke integrations.",
  },
}

function parseSection(value: string | null): SettingsSection {
  return NAV_ITEMS.some((item) => item.key === value) ? (value as SettingsSection) : "organization"
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground/70">{description}</p>
    </div>
  )
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-card">
      <div className="border-b border-border/40 px-4 py-3">
        <h3 className="text-sm font-medium">{title}</h3>
        {description ? <p className="mt-0.5 text-xs text-muted-foreground/60">{description}</p> : null}
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

export default function SettingsPage() {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const hasScope = useAuthStore((state) => state.hasScope)
  const [activeSection, setActiveSection] = useState<SettingsSection>(() => parseSection(searchParams.get("tab")))
  const [organization, setOrganization] = useState<SettingsOrganization | null>(null)
  const [organizationForm, setOrganizationForm] = useState<SettingsOrganization | null>(null)
  const [profile, setProfile] = useState<SettingsProfile | null>(null)
  const [profileForm, setProfileForm] = useState<SettingsProfile | null>(null)
  const [credentials, setCredentials] = useState<IntegrationCredential[]>([])
  const [chatModels, setChatModels] = useState<LogicalModel[]>([])
  const [embeddingModels, setEmbeddingModels] = useState<LogicalModel[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [organizationError, setOrganizationError] = useState<string | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [integrationsError, setIntegrationsError] = useState<string | null>(null)
  const [organizationSaving, setOrganizationSaving] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [auditResourceId, setAuditResourceId] = useState<string | null>(null)

  const canManageOrganization = hasScope("organizations.write")
  const canManageCredentials = hasScope("credentials.write")

  const fetchData = async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const [orgData, profileData, credentialsData, chatData, embeddingData] = await Promise.all([
        settingsOrgService.getOrganization(),
        settingsProfileService.getProfile(),
        credentialsService.listCredentials(undefined, { limit: 100, view: "summary" }),
        modelsService.listModels("chat", "active", 0, 100, "full"),
        modelsService.listModels("embedding", "active", 0, 100, "full"),
      ])
      setOrganization(orgData)
      setOrganizationForm(orgData)
      setProfile(profileData)
      setProfileForm(profileData)
      setCredentials(credentialsData.items)
      setChatModels(chatData.items)
      setEmbeddingModels(embeddingData.items)
      setOrganizationError(null)
      setProfileError(null)
      setIntegrationsError(null)
    } catch (error) {
      setFetchError(formatHttpErrorMessage(error, "Failed to load settings."))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchData()
  }, [])

  useEffect(() => {
    const nextSection = parseSection(searchParams.get("tab"))
    setActiveSection((currentSection) => (currentSection === nextSection ? currentSection : nextSection))
  }, [searchParams])

  const handleSectionChange = (section: SettingsSection) => {
    setActiveSection(section)
    const params = new URLSearchParams(searchParams.toString())
    if (section === "organization") {
      params.delete("tab")
    } else {
      params.set("tab", section)
    }
    const nextQuery = params.toString()
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false })
  }

  const groupedCredentials = useMemo(() => {
    return credentials.reduce<Record<string, IntegrationCredential[]>>((acc, credential) => {
      const key = credential.category
      acc[key] = [...(acc[key] ?? []), credential]
      return acc
    }, {})
  }, [credentials])

  const saveOrganization = async () => {
    if (!organizationForm) return
    setOrganizationSaving(true)
    setOrganizationError(null)
    try {
      const updated = await settingsOrgService.updateOrganization({
        name: organizationForm.name,
        slug: organizationForm.slug,
        status: organizationForm.status,
        default_chat_model_id: organizationForm.default_chat_model_id,
        default_embedding_model_id: organizationForm.default_embedding_model_id,
        default_retrieval_policy: organizationForm.default_retrieval_policy,
      })
      setOrganization(updated)
      setOrganizationForm(updated)
    } catch (error) {
      setOrganizationError(formatHttpErrorMessage(error, "Failed to update organization settings."))
    } finally {
      setOrganizationSaving(false)
    }
  }

  const saveProfile = async () => {
    if (!profileForm) return
    setProfileSaving(true)
    setProfileError(null)
    try {
      const updated = await settingsProfileService.updateProfile({
        full_name: profileForm.full_name,
        avatar: profileForm.avatar,
      })
      setProfile(updated)
      setProfileForm(updated)
    } catch (error) {
      setProfileError(formatHttpErrorMessage(error, "Failed to update profile."))
    } finally {
      setProfileSaving(false)
    }
  }

  const renderOrganization = () => (
    <div className="space-y-6">
      <SectionHeader title="Organization" description="General organization identity and default pointers." />

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <div className="space-y-5">
          <h3 className="border-b border-border/40 pb-2 text-sm font-semibold text-foreground">Identity</h3>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Organization Name</Label>
              <Input
                value={organizationForm?.name || ""}
                onChange={(e) => setOrganizationForm((prev) => prev ? { ...prev, name: e.target.value } : prev)}
                disabled={!canManageOrganization}
                className="h-9 w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Slug</Label>
              <Input
                value={organizationForm?.slug || ""}
                onChange={(e) => setOrganizationForm((prev) => prev ? { ...prev, slug: e.target.value } : prev)}
                disabled={!canManageOrganization}
                className="h-9 w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Status</Label>
              <Select
                value={organizationForm?.status || "active"}
                onValueChange={(value) => setOrganizationForm((prev) => prev ? { ...prev, status: value } : prev)}
                disabled={!canManageOrganization}
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

        <div className="space-y-5">
          <h3 className="border-b border-border/40 pb-2 text-sm font-semibold text-foreground">Defaults</h3>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Default Chat Model</Label>
              <Select
                value={organizationForm?.default_chat_model_id || "none"}
                onValueChange={(value) =>
                  setOrganizationForm((prev) => prev ? { ...prev, default_chat_model_id: value === "none" ? null : value } : prev)
                }
                disabled={!canManageOrganization}
              >
                <SelectTrigger className="h-9 w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {chatModels.map((model) => (
                    <SelectItem key={model.id} value={model.id}>{model.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Default Embedding Model</Label>
              <Select
                value={organizationForm?.default_embedding_model_id || "none"}
                onValueChange={(value) =>
                  setOrganizationForm((prev) => prev ? { ...prev, default_embedding_model_id: value === "none" ? null : value } : prev)
                }
                disabled={!canManageOrganization}
              >
                <SelectTrigger className="h-9 w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {embeddingModels.map((model) => (
                    <SelectItem key={model.id} value={model.id}>{model.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Retrieval Policy</Label>
              <Select
                value={organizationForm?.default_retrieval_policy || "none"}
                onValueChange={(value) =>
                  setOrganizationForm((prev) => prev ? { ...prev, default_retrieval_policy: value === "none" ? null : value } : prev)
                }
                disabled={!canManageOrganization}
              >
                <SelectTrigger className="h-9 w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="semantic_only">Semantic Only</SelectItem>
                  <SelectItem value="hybrid">Hybrid</SelectItem>
                  <SelectItem value="keyword_only">Keyword Only</SelectItem>
                  <SelectItem value="recency_boosted">Recency Boosted</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </div>

      {!canManageOrganization && (
        <p className="mt-2 text-xs text-muted-foreground/60">Read-only access. Contact an admin to make changes.</p>
      )}

      {organizationError && <p className="text-sm text-destructive">{organizationError}</p>}

      <div className={cn("mt-6 flex gap-2 border-t border-border/40 pt-6", isRTL ? "justify-start" : "justify-end")}>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={organizationSaving || profileSaving}>
          Reset
        </Button>
        <Button size="sm" onClick={saveOrganization} disabled={!canManageOrganization || organizationSaving}>
          {organizationSaving ? <span className="mr-2">Saving...</span> : null}
          Save Changes
        </Button>
      </div>
    </div>
  )

  const renderProfile = () => (
    <div className="space-y-6">
      <SectionHeader title="Profile" description="Personal identity for the signed-in user." />

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <div className="space-y-5">
          <h3 className="border-b border-border/40 pb-2 text-sm font-semibold text-foreground">Identity</h3>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Email</Label>
              <Input value={profile?.email || ""} readOnly className="h-9 w-full" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Full Name</Label>
              <Input
                value={profileForm?.full_name || ""}
                onChange={(e) => setProfileForm((prev) => prev ? { ...prev, full_name: e.target.value } : prev)}
                className="h-9 w-full"
              />
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <h3 className="border-b border-border/40 pb-2 text-sm font-semibold text-foreground">Account</h3>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Avatar URL</Label>
              <Input
                value={profileForm?.avatar || ""}
                onChange={(e) => setProfileForm((prev) => prev ? { ...prev, avatar: e.target.value } : prev)}
                className="h-9 w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-muted-foreground">Role</Label>
              <Input value={profile?.role || ""} readOnly className="h-9 w-full" />
            </div>
          </div>
        </div>
      </div>

      {profileError && <p className="text-sm text-destructive">{profileError}</p>}

      <div className={cn("mt-6 flex gap-2 border-t border-border/40 pt-6", isRTL ? "justify-start" : "justify-end")}>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={profileSaving || organizationSaving}>
          Reset
        </Button>
        <Button size="sm" onClick={saveProfile} disabled={profileSaving}>
          {profileSaving ? <span className="mr-2">Saving...</span> : null}
          Save Changes
        </Button>
      </div>
    </div>
  )

  const renderIntegrations = () => (
    <div>
      <SectionHeader title="Credentials" description="Manage organization-scoped credentials. Secret values are write-only." />

      {integrationsError && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {integrationsError}
        </div>
      )}

      <div className="space-y-6">
        {Object.entries(CATEGORY_LABELS).map(([category, meta]) => {
          const items = groupedCredentials[category] || []
          return (
            <div key={category} className="rounded-lg border border-border/50 bg-card">
              <div className="flex items-center justify-between border-b border-border/40 px-4 py-3">
                <div>
                  <h3 className="text-sm font-medium">{meta.title}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground/60">{meta.description}</p>
                </div>
                <CredentialFormDialog mode="create" category={category as any} disabled={!canManageCredentials} onSaved={fetchData} />
              </div>

              {items.length === 0 ? (
                <div className="px-4 py-6 text-center">
                  <p className="text-xs text-muted-foreground/50">No credentials configured.</p>
                </div>
              ) : (
                <div className="divide-y divide-border/30">
                  {items.map((credential) => (
                    <div key={credential.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-mono text-sm font-medium">{credential.provider_key}</span>
                          <span className="flex shrink-0 items-center gap-1">
                            <span className={cn("h-1.5 w-1.5 rounded-full", credential.is_enabled ? "bg-emerald-500" : "bg-zinc-400")} />
                            <span className="text-xs text-muted-foreground/60">{credential.is_enabled ? "Active" : "Disabled"}</span>
                          </span>
                        </div>
                        <div className="mt-0.5 flex items-center gap-2">
                          <span className="font-mono text-xs text-muted-foreground/50">{credential.display_name}</span>
                          {credential.credential_keys.length > 0 ? (
                            <>
                              <span className="text-muted-foreground/30">·</span>
                              <span className="text-xs text-muted-foreground/40">
                                {credential.credential_keys.length} key{credential.credential_keys.length !== 1 ? "s" : ""}
                              </span>
                            </>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <CredentialFormDialog mode="edit" category={credential.category} credential={credential} disabled={!canManageCredentials} onSaved={fetchData} />
                        <CredentialDeleteDialog credential={credential} disabled={!canManageCredentials} onDeleted={fetchData} onError={(message) => setIntegrationsError(message || null)} />
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

  const renderSection = () => {
    switch (activeSection) {
      case "organization":
        return renderOrganization()
      case "profile":
        return renderProfile()
      case "people_permissions":
        return <PeoplePermissionsSection />
      case "projects":
        return <ProjectsSection onOpenAudit={(resourceId) => {
          setAuditResourceId(resourceId)
          handleSectionChange("audit_logs")
        }} />
      case "api_keys":
        return <ApiKeysSection />
      case "limits":
        return <LimitsSection />
      case "audit_logs":
        return <AuditLogsSection initialResourceId={auditResourceId} />
      case "integrations":
        return renderIntegrations()
      case "mcp_servers":
        return <McpSettingsPage />
      default:
        return null
    }
  }

  return (
    <div className="flex h-full w-full flex-col" dir={direction}>
      <AdminPageHeader>
        <CustomBreadcrumb items={[{ label: "Settings", href: "/admin/settings", active: true }]} />
      </AdminPageHeader>

      <div className="flex flex-1 overflow-hidden">
        <nav className="hidden w-56 shrink-0 overflow-y-auto p-3 sm:block">
          <div className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = activeSection === item.key
              return (
                <button
                  key={item.key}
                  onClick={() => handleSectionChange(item.key)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                    isActive ? "bg-muted/60 text-foreground font-medium" : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {item.label}
                </button>
              )
            })}
          </div>
        </nav>

        <div className="shrink-0 border-b border-border/40 px-4 py-2 flex gap-1 overflow-x-auto sm:hidden">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => handleSectionChange(item.key)}
              className={cn(
                "whitespace-nowrap rounded-md px-3 py-1.5 text-xs transition-colors",
                activeSection === item.key ? "bg-muted/60 text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <main className="flex-1 overflow-y-auto" data-admin-page-scroll>
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
            {loading ? (
              <div className="space-y-6 p-6">
                <div className="space-y-2">
                  <div className="h-4 w-32 rounded bg-muted" />
                  <div className="h-3 w-56 rounded bg-muted" />
                </div>
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex gap-6 border-b border-border/40 py-4">
                    <div className="h-4 w-28 rounded bg-muted" />
                    <div className="h-9 max-w-md flex-1 rounded bg-muted" />
                  </div>
                ))}
              </div>
            ) : fetchError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {fetchError}
              </div>
            ) : (
              renderSection()
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
