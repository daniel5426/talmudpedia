"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { resourcePoliciesService } from "@/services/resource-policies"
import type {
  ResourcePolicySet,
  ResourcePolicyAssignment,
  ResourcePolicyRule,
  ResourcePolicyResourceType,
  ResourcePolicyRuleType,
  ResourcePolicyPrincipalType,
  CreatePolicyRuleRequest,
  UpsertAssignmentRequest,
} from "@/services/resource-policies"
import { agentService } from "@/services/agent"
import type { Agent, LogicalModel, ToolDefinition } from "@/services/agent"
import { modelsService } from "@/services/models"
import { toolsService } from "@/services/tools"
import { knowledgeStoresService } from "@/services/knowledge-stores"
import type { KnowledgeStore } from "@/services/knowledge-stores"
import { publishedAppsService } from "@/services/published-apps"
import type { PublishedApp } from "@/services/published-apps"
import { adminService } from "@/services/admin"
import type { User } from "@/services/types"
import { AdminPageHeader } from "@/components/admin/AdminPageHeader"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { useUrlEnumState } from "@/hooks/useUrlEnumState"
import {
  Plus,
  Search,
  MoreHorizontal,
  Trash2,
  Edit2,
  Loader2,
  ScrollText,
  Shield,
  Link2,
  Unlink,
  Layers,
  Target,
  UserCheck,
  Bot,
  Globe,
  Hash,
  Gauge,
  ChevronRight,
  X,
  AlertCircle,
  ArrowLeft,
} from "lucide-react"

/* ───────────────────────────── Constants ───────────────────────────── */

type PageSection = "sets" | "assignments" | "defaults"
const RESOURCE_POLICY_SECTIONS = ["sets", "assignments", "defaults"] as const

const NAV_ITEMS: Array<{ key: PageSection; label: string; icon: React.ElementType }> = [
  { key: "sets", label: "Policy Sets", icon: Layers },
  { key: "assignments", label: "Assignments", icon: Target },
  { key: "defaults", label: "Defaults", icon: Shield },
]

const RESOURCE_TYPE_LABELS: Record<ResourcePolicyResourceType, string> = {
  agent: "Agent",
  tool: "Tool",
  knowledge_store: "Knowledge Store",
  model: "Model",
}

const RULE_TYPE_LABELS: Record<ResourcePolicyRuleType, string> = {
  allow: "Allow",
  quota: "Quota",
}

const PRINCIPAL_TYPE_LABELS: Record<ResourcePolicyPrincipalType, string> = {
  tenant_user: "Tenant User",
  published_app_account: "Published App Account",
  embedded_external_user: "Embedded External User",
}

const RESOURCE_TYPE_COLORS: Record<ResourcePolicyResourceType, string> = {
  agent: "bg-violet-500/15 text-violet-700 dark:text-violet-400",
  tool: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  knowledge_store: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  model: "bg-rose-500/15 text-rose-700 dark:text-rose-400",
}

/* ───────────────────────────── Page ───────────────────────────── */

export default function ResourcePoliciesPage() {
  const [section, setSection] = useUrlEnumState({
    key: "section",
    allowedValues: RESOURCE_POLICY_SECTIONS,
    fallback: "sets",
  })
  const [searchQuery, setSearchQuery] = useState("")

  // Data
  const [policySets, setPolicySets] = useState<ResourcePolicySet[]>([])
  const [assignments, setAssignments] = useState<ResourcePolicyAssignment[]>([])
  const [loading, setLoading] = useState(true)

  // Resource lookups
  const [agents, setAgents] = useState<Agent[]>([])
  const [models, setModels] = useState<LogicalModel[]>([])
  const [tools, setTools] = useState<ToolDefinition[]>([])
  const [knowledgeStores, setKnowledgeStores] = useState<KnowledgeStore[]>([])
  const [publishedApps, setPublishedApps] = useState<PublishedApp[]>([])
  const [users, setUsers] = useState<User[]>([])

  // Modals
  const [policySetModal, setPolicySetModal] = useState<{ open: boolean; editing: ResourcePolicySet | null }>({ open: false, editing: null })
  const [deleteTarget, setDeleteTarget] = useState<ResourcePolicySet | null>(null)
  const [detailSet, setDetailSet] = useState<ResourcePolicySet | null>(null)
  const [assignmentModal, setAssignmentModal] = useState(false)
  const [deleteAssignmentTarget, setDeleteAssignmentTarget] = useState<ResourcePolicyAssignment | null>(null)

  // Mutation state
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /* ── Fetch ── */
  const fetchPolicySets = useCallback(async () => {
    try {
      const data = await resourcePoliciesService.listPolicySets()
      setPolicySets(data)
    } catch {
      // noop
    }
  }, [])

  const fetchAssignments = useCallback(async () => {
    try {
      const data = await resourcePoliciesService.listAssignments()
      setAssignments(data)
    } catch {
      // noop
    }
  }, [])

  const fetchResources = useCallback(async () => {
    try {
      const [agentsRes, modelsRes, toolsRes, ksRes, appsRes, usersRes] = await Promise.allSettled([
        agentService.listAgents({ limit: 200, compact: true }),
        modelsService.listModels(),
        toolsService.listTools(),
        knowledgeStoresService.list(),
        publishedAppsService.list(),
        adminService.getUsers(1, 200),
      ])
      if (agentsRes.status === "fulfilled") setAgents(agentsRes.value.agents || [])
      if (modelsRes.status === "fulfilled") setModels(modelsRes.value.models || [])
      if (toolsRes.status === "fulfilled") setTools(toolsRes.value.tools || [])
      if (ksRes.status === "fulfilled") setKnowledgeStores(ksRes.value || [])
      if (appsRes.status === "fulfilled") setPublishedApps(appsRes.value || [])
      if (usersRes.status === "fulfilled") setUsers(usersRes.value.items || [])
    } catch {
      // noop
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    Promise.all([fetchPolicySets(), fetchAssignments(), fetchResources()]).finally(() =>
      setLoading(false)
    )
  }, [fetchPolicySets, fetchAssignments, fetchResources])

  /* ── Lookups ── */
  const policySetMap = useMemo(() => {
    const m = new Map<string, ResourcePolicySet>()
    policySets.forEach((ps) => m.set(ps.id, ps))
    return m
  }, [policySets])

  const agentMap = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents])
  const modelMap = useMemo(() => new Map(models.map((m) => [m.id, m])), [models])
  const toolMap = useMemo(() => new Map(tools.map((t) => [t.id, t])), [tools])
  const ksMap = useMemo(() => new Map(knowledgeStores.map((k) => [k.id, k])), [knowledgeStores])
  const appMap = useMemo(() => new Map(publishedApps.map((a) => [a.id, a])), [publishedApps])
  const userMap = useMemo(() => new Map(users.map((u) => [u.id, u])), [users])

  const resolveResourceName = useCallback(
    (type: ResourcePolicyResourceType, id: string): string => {
      switch (type) {
        case "agent": return agentMap.get(id)?.name || id.slice(0, 8)
        case "model": return modelMap.get(id)?.name || id.slice(0, 8)
        case "tool": return toolMap.get(id)?.name || id.slice(0, 8)
        case "knowledge_store": return ksMap.get(id)?.name || id.slice(0, 8)
        default: return id.slice(0, 8)
      }
    },
    [agentMap, modelMap, toolMap, ksMap]
  )

  /* ── Filtered sets ── */
  const filteredSets = useMemo(() => {
    if (!searchQuery) return policySets
    const q = searchQuery.toLowerCase()
    return policySets.filter(
      (ps) =>
        ps.name.toLowerCase().includes(q) ||
        (ps.description || "").toLowerCase().includes(q)
    )
  }, [policySets, searchQuery])

  const filteredAssignments = useMemo(() => {
    if (!searchQuery) return assignments
    const q = searchQuery.toLowerCase()
    return assignments.filter((a) => {
      const psName = policySetMap.get(a.policy_set_id)?.name || ""
      return (
        psName.toLowerCase().includes(q) ||
        a.principal_type.toLowerCase().includes(q) ||
        (a.external_user_id || "").toLowerCase().includes(q)
      )
    })
  }, [assignments, searchQuery, policySetMap])

  /* ── Refresh detail after mutation ── */
  const refreshDetailSet = useCallback(
    async (id: string) => {
      try {
        const updated = await resourcePoliciesService.getPolicySet(id)
        setDetailSet(updated)
        await fetchPolicySets()
      } catch {
        // noop
      }
    },
    [fetchPolicySets]
  )

  /* ── Render ── */
  return (
    <div className="flex h-full w-full flex-col">
      {/* Header */}
      <AdminPageHeader>
        <CustomBreadcrumb
          items={[
            { label: "Security & Org", href: "/admin/security" },
            { label: "Resource Policies", active: true },
          ]}
        />
        {section === "sets" && (
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => setPolicySetModal({ open: true, editing: null })}
          >
            <Plus className="h-3.5 w-3.5" />
            New Policy Set
          </Button>
        )}
        {section === "assignments" && (
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => setAssignmentModal(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            New Assignment
          </Button>
        )}
      </AdminPageHeader>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 px-3 py-3 shrink-0">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={section === "sets" ? "Search policy sets..." : section === "assignments" ? "Search assignments..." : "Search..."}
            className="pl-8 h-8 text-sm border-border/50 placeholder:text-muted-foreground/50"
          />
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-muted/50 p-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.key}
                onClick={() => { setSection(item.key); setSearchQuery("") }}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors",
                  section === item.key
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3 w-3" />
                {item.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto bg-muted/40 mx-3 mb-4 rounded-2xl">
        <div className="px-6 pb-6 pt-6">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-[200px] w-full rounded-xl" />
              ))}
            </div>
          ) : section === "sets" ? (
            <PolicySetsGrid
              policySets={filteredSets}
              policySetMap={policySetMap}
              resolveResourceName={resolveResourceName}
              searchQuery={searchQuery}
              onEdit={(ps) => setPolicySetModal({ open: true, editing: ps })}
              onDelete={(ps) => setDeleteTarget(ps)}
              onDetail={(ps) => setDetailSet(ps)}
              onCreate={() => setPolicySetModal({ open: true, editing: null })}
            />
          ) : section === "assignments" ? (
            <AssignmentsTable
              assignments={filteredAssignments}
              policySetMap={policySetMap}
              userMap={userMap}
              appMap={appMap}
              agentMap={agentMap}
              searchQuery={searchQuery}
              onDelete={(a) => setDeleteAssignmentTarget(a)}
              onCreate={() => setAssignmentModal(true)}
            />
          ) : (
            <DefaultsSection
              publishedApps={publishedApps}
              agents={agents}
              policySets={policySets}
            />
          )}
        </div>
      </div>

      {/* ── Modals ── */}

      {/* Create/Edit Policy Set (standalone — used for create from header + card dropdown edit) */}
      <PolicySetFormDialog
        open={policySetModal.open}
        editing={policySetModal.editing}
        onClose={() => { setPolicySetModal({ open: false, editing: null }); setError(null) }}
        onSaved={() => {
          setPolicySetModal({ open: false, editing: null })
          setError(null)
          fetchPolicySets()
        }}
      />

      {/* Delete Policy Set */}
      <DeleteDialog
        open={!!deleteTarget}
        title="Delete Policy Set"
        description={<>Are you sure you want to delete <strong>{deleteTarget?.name}</strong>? All rules, includes, and assignments referencing this set will be removed.</>}
        onClose={() => { setDeleteTarget(null); setError(null) }}
        onConfirm={async () => {
          if (!deleteTarget) return
          setDeleting(true)
          setError(null)
          try {
            await resourcePoliciesService.deletePolicySet(deleteTarget.id)
            setDeleteTarget(null)
            if (detailSet?.id === deleteTarget.id) setDetailSet(null)
            await fetchPolicySets()
            await fetchAssignments()
          } catch (err: any) {
            setError(String(err?.message || err))
          } finally {
            setDeleting(false)
          }
        }}
        loading={deleting}
        error={error}
      />

      {/* Policy Set Detail — multi-view dialog (detail / add-rule / edit) */}
      <PolicySetDetailDialog
        policySet={detailSet}
        policySetMap={policySetMap}
        policySets={policySets}
        resolveResourceName={resolveResourceName}
        agents={agents}
        models={models}
        tools={tools}
        knowledgeStores={knowledgeStores}
        onClose={() => setDetailSet(null)}
        onRefresh={refreshDetailSet}
      />

      {/* Create Assignment */}
      <AssignmentFormDialog
        open={assignmentModal}
        policySets={policySets}
        users={users}
        publishedApps={publishedApps}
        agents={agents}
        onClose={() => { setAssignmentModal(false); setError(null) }}
        onSaved={() => {
          setAssignmentModal(false)
          setError(null)
          fetchAssignments()
        }}
      />

      {/* Delete Assignment */}
      <DeleteDialog
        open={!!deleteAssignmentTarget}
        title="Remove Assignment"
        description="Are you sure you want to remove this policy assignment?"
        onClose={() => { setDeleteAssignmentTarget(null); setError(null) }}
        onConfirm={async () => {
          if (!deleteAssignmentTarget) return
          setDeleting(true)
          setError(null)
          try {
            await resourcePoliciesService.deleteAssignment({
              principal_type: deleteAssignmentTarget.principal_type,
              user_id: deleteAssignmentTarget.user_id || undefined,
              published_app_account_id: deleteAssignmentTarget.published_app_account_id || undefined,
              embedded_agent_id: deleteAssignmentTarget.embedded_agent_id || undefined,
              external_user_id: deleteAssignmentTarget.external_user_id || undefined,
            })
            setDeleteAssignmentTarget(null)
            await fetchAssignments()
          } catch (err: any) {
            setError(String(err?.message || err))
          } finally {
            setDeleting(false)
          }
        }}
        loading={deleting}
        error={error}
      />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   Sub-Components
   ═══════════════════════════════════════════════════════════════════════ */

/* ── Policy Sets Grid ── */

function PolicySetsGrid({
  policySets,
  policySetMap,
  resolveResourceName,
  searchQuery,
  onEdit,
  onDelete,
  onDetail,
  onCreate,
}: {
  policySets: ResourcePolicySet[]
  policySetMap: Map<string, ResourcePolicySet>
  resolveResourceName: (type: ResourcePolicyResourceType, id: string) => string
  searchQuery: string
  onEdit: (ps: ResourcePolicySet) => void
  onDelete: (ps: ResourcePolicySet) => void
  onDetail: (ps: ResourcePolicySet) => void
  onCreate: () => void
}) {
  if (policySets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
          <ScrollText className="h-6 w-6 text-muted-foreground/40" />
        </div>
        <h3 className="text-sm font-medium text-foreground mb-1">
          {searchQuery ? "No policy sets match your search" : "No policy sets yet"}
        </h3>
        <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
          {searchQuery
            ? "Try a different search term."
            : "Create your first resource policy set to control access and quotas."}
        </p>
        {!searchQuery && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onCreate}>
            <Plus className="h-3.5 w-3.5" />
            Create Policy Set
          </Button>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {policySets.map((ps) => {
          const allowRules = ps.rules.filter((r) => r.rule_type === "allow")
          const quotaRules = ps.rules.filter((r) => r.rule_type === "quota")
          const includedCount = ps.included_policy_set_ids.length

          return (
            <div
              key={ps.id}
              onClick={() => onDetail(ps)}
              className="group relative flex min-h-[200px] flex-col justify-between bg-background rounded-xl p-5 cursor-pointer transition-all duration-200 hover:ring-1 hover:ring-primary/20 overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-2">
                  <div className={cn("h-2 w-2 rounded-full", ps.is_active ? "bg-emerald-500" : "bg-zinc-400")} />
                  <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                    {ps.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
                <div
                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => e.stopPropagation()}
                >
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-6 w-6 -mr-1">
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-44">
                      <DropdownMenuItem onClick={() => onEdit(ps)}>
                        <Edit2 className="h-3.5 w-3.5 mr-2" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() => onDelete(ps)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="h-3.5 w-3.5 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              {/* Content */}
              <div className="relative z-10 my-2 flex-1">
                <h3 className="text-base font-bold tracking-tight text-foreground truncate group-hover:text-primary transition-colors">
                  {ps.name}
                </h3>
                {ps.description && (
                  <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 leading-relaxed">
                    {ps.description}
                  </p>
                )}
                {/* Rule badges */}
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {allowRules.length > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 rounded-full">
                      <Shield className="h-2.5 w-2.5" />
                      {allowRules.length} allow
                    </span>
                  )}
                  {quotaRules.length > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-amber-500/10 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded-full">
                      <Gauge className="h-2.5 w-2.5" />
                      {quotaRules.length} quota
                    </span>
                  )}
                  {includedCount > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-blue-500/10 text-blue-700 dark:text-blue-400 px-2 py-0.5 rounded-full">
                      <Link2 className="h-2.5 w-2.5" />
                      {includedCount} include{includedCount > 1 ? "s" : ""}
                    </span>
                  )}
                  {ps.rules.length === 0 && includedCount === 0 && (
                    <span className="text-[10px] text-muted-foreground/60 italic">No rules</span>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between relative z-10 pt-2 border-t border-border/30">
                <span className="text-[11px] text-muted-foreground font-mono">
                  {ps.rules.length} rule{ps.rules.length !== 1 ? "s" : ""}
                </span>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary/60 transition-colors" />
              </div>
            </div>
          )
        })}
      </div>
      {policySets.length > 0 && (
        <p className="text-xs text-muted-foreground pt-4 px-1">
          {policySets.length} policy set{policySets.length !== 1 ? "s" : ""}
        </p>
      )}
    </>
  )
}

/* ── Policy Set Detail Dialog (multi-view: detail / add-rule / edit) ── */

type DetailView = "detail" | "add-rule" | "edit"

function PolicySetDetailDialog({
  policySet,
  policySetMap,
  policySets,
  resolveResourceName,
  agents,
  models,
  tools,
  knowledgeStores,
  onClose,
  onRefresh,
}: {
  policySet: ResourcePolicySet | null
  policySetMap: Map<string, ResourcePolicySet>
  policySets: ResourcePolicySet[]
  resolveResourceName: (type: ResourcePolicyResourceType, id: string) => string
  agents: Agent[]
  models: LogicalModel[]
  tools: ToolDefinition[]
  knowledgeStores: KnowledgeStore[]
  onClose: () => void
  onRefresh: (id: string) => Promise<void>
}) {
  const [view, setView] = useState<DetailView>("detail")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [addingInclude, setAddingInclude] = useState(false)

  // Rule form state
  const [ruleType, setRuleType] = useState<ResourcePolicyRuleType>("allow")
  const [resourceType, setResourceType] = useState<ResourcePolicyResourceType>("agent")
  const [resourceId, setResourceId] = useState("")
  const [quotaLimit, setQuotaLimit] = useState("")

  // Edit form state
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editIsActive, setEditIsActive] = useState(true)

  // Reset view when a different policy set is opened
  const prevIdRef = useRef<string | null>(null)
  useEffect(() => {
    if (policySet?.id && policySet.id !== prevIdRef.current) {
      prevIdRef.current = policySet.id
      setView("detail")
      setError(null)
    }
    if (!policySet) {
      prevIdRef.current = null
    }
  }, [policySet?.id, policySet])

  // Resource options for rule form
  const resourceOptions = useMemo(() => {
    switch (resourceType) {
      case "agent": return agents.map((a) => ({ id: a.id, name: a.name }))
      case "model": return models.map((m) => ({ id: m.id, name: m.name }))
      case "tool": return tools.map((t) => ({ id: t.id, name: t.name }))
      case "knowledge_store": return knowledgeStores.map((k) => ({ id: k.id, name: k.name }))
      default: return []
    }
  }, [resourceType, agents, models, tools, knowledgeStores])

  // Available sets for include dropdown
  const availableIncludeSets = useMemo(() => {
    if (!policySet) return []
    const alreadyIncluded = new Set(policySet.included_policy_set_ids)
    return policySets.filter((ps) => ps.id !== policySet.id && !alreadyIncluded.has(ps.id))
  }, [policySets, policySet])

  /* ── View transitions ── */

  const handleGoToAddRule = () => {
    setRuleType("allow")
    setResourceType("agent")
    setResourceId("")
    setQuotaLimit("")
    setError(null)
    setView("add-rule")
  }

  const handleGoToEdit = () => {
    if (!policySet) return
    setEditName(policySet.name)
    setEditDescription(policySet.description || "")
    setEditIsActive(policySet.is_active)
    setError(null)
    setView("edit")
  }

  /* ── Mutations ── */

  const handleDeleteRule = async (ruleId: string) => {
    if (!policySet) return
    try {
      await resourcePoliciesService.deleteRule(ruleId)
      await onRefresh(policySet.id)
    } catch (err: any) {
      setError(String(err?.message || err))
    }
  }

  const handleAddInclude = async (includedSetId: string) => {
    if (!policySet) return
    setAddingInclude(true)
    try {
      await resourcePoliciesService.addInclude(policySet.id, includedSetId)
      await onRefresh(policySet.id)
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setAddingInclude(false)
    }
  }

  const handleRemoveInclude = async (includedId: string) => {
    if (!policySet) return
    try {
      await resourcePoliciesService.removeInclude(policySet.id, includedId)
      await onRefresh(policySet.id)
    } catch (err: any) {
      setError(String(err?.message || err))
    }
  }

  const handleSaveRule = async () => {
    if (!policySet || !resourceId) return
    setSaving(true)
    setError(null)
    try {
      const req: CreatePolicyRuleRequest = {
        resource_type: resourceType,
        resource_id: resourceId,
        rule_type: ruleType,
      }
      if (ruleType === "quota") {
        req.quota_unit = "tokens"
        req.quota_window = "monthly"
        req.quota_limit = parseInt(quotaLimit) || 0
      }
      await resourcePoliciesService.createRule(policySet.id, req)
      await onRefresh(policySet.id)
      setView("detail")
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!policySet || !editName.trim()) return
    setSaving(true)
    setError(null)
    try {
      await resourcePoliciesService.updatePolicySet(policySet.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        is_active: editIsActive,
      })
      await onRefresh(policySet.id)
      setView("detail")
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }

  if (!policySet) return null

  return (
    <Dialog open={!!policySet} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden p-0">
        <div key={view} className="animate-in fade-in slide-in-from-bottom-1 duration-200 overflow-y-auto max-h-[85vh] p-6">

          {/* ═══ Detail View ═══ */}
          {view === "detail" && (
            <>
              <DialogHeader>
                <div className="flex items-center gap-3">
                  <div className={cn("h-2.5 w-2.5 rounded-full shrink-0", policySet.is_active ? "bg-emerald-500" : "bg-zinc-400")} />
                  <DialogTitle className="text-lg">{policySet.name}</DialogTitle>
                </div>
                {policySet.description && (
                  <DialogDescription>{policySet.description}</DialogDescription>
                )}
              </DialogHeader>

              {/* Rules Section */}
              <div className="space-y-3 mt-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-foreground">Rules</h4>
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={handleGoToAddRule}>
                    <Plus className="h-3 w-3" />
                    Add Rule
                  </Button>
                </div>

                {policySet.rules.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
                    <p className="text-xs text-muted-foreground">No rules. Add a rule to define resource access or quotas.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {policySet.rules.map((rule) => (
                      <div
                        key={rule.id}
                        className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/30 px-3 py-2.5 group/rule"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <Badge
                            variant="secondary"
                            className={cn("text-[10px] shrink-0", RESOURCE_TYPE_COLORS[rule.resource_type])}
                          >
                            {RESOURCE_TYPE_LABELS[rule.resource_type]}
                          </Badge>
                          <span className="text-sm font-medium truncate">
                            {resolveResourceName(rule.resource_type, rule.resource_id)}
                          </span>
                          <Badge variant="outline" className="text-[10px] shrink-0">
                            {rule.rule_type === "allow" ? (
                              <><Shield className="h-2.5 w-2.5 mr-1" />Allow</>
                            ) : (
                              <><Gauge className="h-2.5 w-2.5 mr-1" />Quota</>
                            )}
                          </Badge>
                          {rule.rule_type === "quota" && rule.quota_limit != null && (
                            <span className="text-xs text-muted-foreground font-mono shrink-0">
                              {rule.quota_limit.toLocaleString()} {rule.quota_unit}/{rule.quota_window}
                            </span>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 opacity-0 group-hover/rule:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                          onClick={() => handleDeleteRule(rule.id)}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Includes Section */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-foreground">Included Policy Sets</h4>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={addingInclude}>
                        {addingInclude ? <Loader2 className="h-3 w-3 animate-spin" /> : <Link2 className="h-3 w-3" />}
                        Add Include
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-64">
                      {availableIncludeSets.length === 0 ? (
                        <div className="py-4 text-center text-xs text-muted-foreground">
                          No available policy sets to include.
                        </div>
                      ) : (
                        availableIncludeSets.map((ps) => (
                          <DropdownMenuItem
                            key={ps.id}
                            onClick={() => handleAddInclude(ps.id)}
                            disabled={addingInclude}
                          >
                            <Layers className="h-3.5 w-3.5 mr-2 text-blue-500" />
                            <span className="truncate">{ps.name}</span>
                            {!ps.is_active && (
                              <span className="ml-auto text-[10px] text-muted-foreground pl-2 shrink-0">(inactive)</span>
                            )}
                          </DropdownMenuItem>
                        ))
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {policySet.included_policy_set_ids.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
                    <p className="text-xs text-muted-foreground">No included sets. Include other policy sets to compose rules.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {policySet.included_policy_set_ids.map((includedId) => {
                      const included = policySetMap.get(includedId)
                      return (
                        <div
                          key={includedId}
                          className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/30 px-3 py-2.5 group/inc"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <Layers className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                            <span className="text-sm font-medium truncate">
                              {included?.name || includedId.slice(0, 8)}
                            </span>
                            {included && !included.is_active && (
                              <Badge variant="secondary" className="text-[10px]">Inactive</Badge>
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 opacity-0 group-hover/inc:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                            onClick={() => handleRemoveInclude(includedId)}
                          >
                            <Unlink className="h-3 w-3" />
                          </Button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {error && (
                <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2 mt-3">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <DialogFooter className="pt-4">
                <Button variant="outline" size="sm" onClick={onClose}>
                  Close
                </Button>
                <Button size="sm" className="gap-1.5" onClick={handleGoToEdit}>
                  <Edit2 className="h-3 w-3" />
                  Edit Details
                </Button>
              </DialogFooter>
            </>
          )}

          {/* ═══ Add Rule View ═══ */}
          {view === "add-rule" && (
            <>
              <button
                onClick={() => { setView("detail"); setError(null) }}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mb-4"
              >
                <ArrowLeft className="h-3 w-3" />
                Back
              </button>

              <DialogHeader>
                <DialogTitle>Add Rule</DialogTitle>
                <DialogDescription>
                  Add an access or quota rule to <strong>{policySet.name}</strong>.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 pt-2">
                {/* Rule Type + Resource Type on same row */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Rule Type</Label>
                    <Select
                      value={ruleType}
                      onValueChange={(v) => {
                        const newType = v as ResourcePolicyRuleType
                        setRuleType(newType)
                        if (newType === "quota" && resourceType !== "model") {
                          setResourceType("model")
                          setResourceId("")
                        }
                      }}
                    >
                      <SelectTrigger className="h-8 w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="allow">
                          <span className="flex items-center gap-1.5">
                            <Shield className="h-3 w-3 text-emerald-500" />
                            Allow
                          </span>
                        </SelectItem>
                        <SelectItem value="quota">
                          <span className="flex items-center gap-1.5">
                            <Gauge className="h-3 w-3 text-amber-500" />
                            Quota (model only)
                          </span>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Resource Type</Label>
                    <Select
                      value={resourceType}
                      onValueChange={(v) => { setResourceType(v as ResourcePolicyResourceType); setResourceId("") }}
                      disabled={ruleType === "quota"}
                    >
                      <SelectTrigger className="h-8 w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(Object.entries(RESOURCE_TYPE_LABELS) as [ResourcePolicyResourceType, string][]).map(([val, label]) => (
                          <SelectItem key={val} value={val} disabled={ruleType === "quota" && val !== "model"}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Resource</Label>
                  <Select value={resourceId} onValueChange={setResourceId}>
                    <SelectTrigger className="h-8 w-full">
                      <SelectValue placeholder="Select a resource..." />
                    </SelectTrigger>
                    <SelectContent>
                      {resourceOptions.map((opt) => (
                        <SelectItem key={opt.id} value={opt.id}>
                          {opt.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {ruleType === "quota" && (
                  <div className="space-y-2">
                    <Label>Token Limit (monthly)</Label>
                    <Input
                      type="number"
                      value={quotaLimit}
                      onChange={(e) => setQuotaLimit(e.target.value)}
                      placeholder="e.g. 1000000"
                      min={0}
                    />
                    <p className="text-[11px] text-muted-foreground">
                      Maximum tokens per month for the selected model.
                    </p>
                  </div>
                )}
              </div>

              {error && (
                <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2 mt-4">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-5">
                <Button variant="outline" size="sm" onClick={() => { setView("detail"); setError(null) }}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveRule}
                  disabled={saving || !resourceId || (ruleType === "quota" && !quotaLimit)}
                  className="gap-1.5"
                >
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Add Rule
                </Button>
              </div>
            </>
          )}

          {/* ═══ Edit View ═══ */}
          {view === "edit" && (
            <>
              <button
                onClick={() => { setView("detail"); setError(null) }}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mb-4"
              >
                <ArrowLeft className="h-3 w-3" />
                Back
              </button>

              <DialogHeader>
                <DialogTitle>Edit Policy Set</DialogTitle>
                <DialogDescription>
                  Update the name, description, or status.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="edit-ps-name">Name</Label>
                  <Input
                    id="edit-ps-name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="e.g. Free Tier, Power Users"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-ps-desc">Description</Label>
                  <Textarea
                    id="edit-ps-desc"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Optional description..."
                    rows={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Status</Label>
                  <Select
                    value={editIsActive ? "active" : "inactive"}
                    onValueChange={(v) => setEditIsActive(v === "active")}
                  >
                    <SelectTrigger className="h-8 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="inactive">Inactive</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2 mt-4">
                  <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-5">
                <Button variant="outline" size="sm" onClick={() => { setView("detail"); setError(null) }}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveEdit}
                  disabled={saving || !editName.trim()}
                  className="gap-1.5"
                >
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Save Changes
                </Button>
              </div>
            </>
          )}

        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ── Policy Set Form Dialog (standalone — for create + grid card edit) ── */

function PolicySetFormDialog({
  open,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean
  editing: ResourcePolicySet | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setName(editing?.name || "")
      setDescription(editing?.description || "")
      setIsActive(editing?.is_active ?? true)
      setError(null)
    }
  }, [open, editing])

  const handleSave = async () => {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      if (editing) {
        await resourcePoliciesService.updatePolicySet(editing.id, {
          name: name.trim(),
          description: description.trim() || undefined,
          is_active: isActive,
        })
      } else {
        await resourcePoliciesService.createPolicySet({
          name: name.trim(),
          description: description.trim() || undefined,
          is_active: isActive,
        })
      }
      onSaved()
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit Policy Set" : "Create Policy Set"}</DialogTitle>
          <DialogDescription>
            {editing
              ? "Update the policy set name, description, or status."
              : "Create a new resource policy set to define access rules and quotas."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="ps-name">Name</Label>
            <Input
              id="ps-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Free Tier, Power Users"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ps-desc">Description</Label>
            <Textarea
              id="ps-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description..."
              rows={2}
            />
          </div>
          <div className="space-y-2">
            <Label>Status</Label>
            <Select
              value={isActive ? "active" : "inactive"}
              onValueChange={(v) => setIsActive(v === "active")}
            >
              <SelectTrigger className="h-8 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !name.trim()} className="gap-1.5">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {editing ? "Save Changes" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ── Assignments Table ── */

function AssignmentsTable({
  assignments,
  policySetMap,
  userMap,
  appMap,
  agentMap,
  searchQuery,
  onDelete,
  onCreate,
}: {
  assignments: ResourcePolicyAssignment[]
  policySetMap: Map<string, ResourcePolicySet>
  userMap: Map<string, User>
  appMap: Map<string, PublishedApp>
  agentMap: Map<string, Agent>
  searchQuery: string
  onDelete: (a: ResourcePolicyAssignment) => void
  onCreate: () => void
}) {
  if (assignments.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
          <Target className="h-6 w-6 text-muted-foreground/40" />
        </div>
        <h3 className="text-sm font-medium text-foreground mb-1">
          {searchQuery ? "No assignments match your search" : "No assignments yet"}
        </h3>
        <p className="text-sm text-muted-foreground/70 max-w-[300px] mb-5">
          {searchQuery
            ? "Try a different search term."
            : "Assign policy sets to users, app accounts, or embedded users."}
        </p>
        {!searchQuery && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onCreate}>
            <Plus className="h-3.5 w-3.5" />
            Create Assignment
          </Button>
        )}
      </div>
    )
  }

  const resolvePrincipal = (a: ResourcePolicyAssignment): { icon: React.ElementType; label: string; detail: string } => {
    switch (a.principal_type) {
      case "tenant_user": {
        const user = a.user_id ? userMap.get(a.user_id) : null
        return {
          icon: UserCheck,
          label: user?.display_name || user?.email || a.user_id?.slice(0, 8) || "Unknown",
          detail: user?.email || "",
        }
      }
      case "published_app_account": {
        return {
          icon: Globe,
          label: `App Account ${a.published_app_account_id?.slice(0, 8) || "?"}`,
          detail: "",
        }
      }
      case "embedded_external_user": {
        const agent = a.embedded_agent_id ? agentMap.get(a.embedded_agent_id) : null
        return {
          icon: Bot,
          label: `${agent?.name || a.embedded_agent_id?.slice(0, 8) || "?"}`,
          detail: a.external_user_id || "",
        }
      }
      default:
        return { icon: Hash, label: "Unknown", detail: "" }
    }
  }

  return (
    <div className="space-y-2">
      {assignments.map((a) => {
        const principal = resolvePrincipal(a)
        const PrincipalIcon = principal.icon
        const ps = policySetMap.get(a.policy_set_id)
        return (
          <div
            key={a.id}
            className="flex items-center justify-between rounded-xl bg-background px-4 py-3 group"
          >
            <div className="flex items-center gap-4 min-w-0">
              {/* Principal */}
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                  <PrincipalIcon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{principal.label}</p>
                  {principal.detail && (
                    <p className="text-[11px] text-muted-foreground truncate">{principal.detail}</p>
                  )}
                </div>
              </div>

              {/* Arrow */}
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />

              {/* Policy Set */}
              <div className="flex items-center gap-2 min-w-0">
                <Badge variant="secondary" className="text-xs shrink-0">
                  <ScrollText className="h-3 w-3 mr-1" />
                  {ps?.name || a.policy_set_id.slice(0, 8)}
                </Badge>
              </div>

              {/* Type badge */}
              <Badge variant="outline" className="text-[10px] shrink-0 ml-2">
                {PRINCIPAL_TYPE_LABELS[a.principal_type]}
              </Badge>
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => onDelete(a)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )
      })}
      <p className="text-xs text-muted-foreground pt-2 px-1">
        {assignments.length} assignment{assignments.length !== 1 ? "s" : ""}
      </p>
    </div>
  )
}

/* ── Assignment Form Dialog ── */

function AssignmentFormDialog({
  open,
  policySets,
  users,
  publishedApps,
  agents,
  onClose,
  onSaved,
}: {
  open: boolean
  policySets: ResourcePolicySet[]
  users: User[]
  publishedApps: PublishedApp[]
  agents: Agent[]
  onClose: () => void
  onSaved: () => void
}) {
  const [principalType, setPrincipalType] = useState<ResourcePolicyPrincipalType>("tenant_user")
  const [policySetId, setPolicySetId] = useState("")
  const [userId, setUserId] = useState("")
  const [publishedAppAccountId, setPublishedAppAccountId] = useState("")
  const [embeddedAgentId, setEmbeddedAgentId] = useState("")
  const [externalUserId, setExternalUserId] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setPrincipalType("tenant_user")
      setPolicySetId("")
      setUserId("")
      setPublishedAppAccountId("")
      setEmbeddedAgentId("")
      setExternalUserId("")
      setError(null)
    }
  }, [open])

  const isValid = () => {
    if (!policySetId) return false
    switch (principalType) {
      case "tenant_user": return !!userId
      case "published_app_account": return !!publishedAppAccountId
      case "embedded_external_user": return !!embeddedAgentId && !!externalUserId.trim()
    }
  }

  const handleSave = async () => {
    if (!isValid()) return
    setSaving(true)
    setError(null)
    try {
      const req: UpsertAssignmentRequest = {
        principal_type: principalType,
        policy_set_id: policySetId,
      }
      if (principalType === "tenant_user") req.user_id = userId
      if (principalType === "published_app_account") req.published_app_account_id = publishedAppAccountId
      if (principalType === "embedded_external_user") {
        req.embedded_agent_id = embeddedAgentId
        req.external_user_id = externalUserId.trim()
      }
      await resourcePoliciesService.upsertAssignment(req)
      onSaved()
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }

  const activePolicySets = policySets.filter((ps) => ps.is_active)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create Assignment</DialogTitle>
          <DialogDescription>
            Assign a policy set to a principal. Direct assignments override defaults.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Policy Set</Label>
            <Select value={policySetId} onValueChange={setPolicySetId}>
              <SelectTrigger className="h-8 w-full">
                <SelectValue placeholder="Select a policy set..." />
              </SelectTrigger>
              <SelectContent>
                {activePolicySets.map((ps) => (
                  <SelectItem key={ps.id} value={ps.id}>{ps.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Principal Type</Label>
            <Select value={principalType} onValueChange={(v) => setPrincipalType(v as ResourcePolicyPrincipalType)}>
              <SelectTrigger className="h-8 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tenant_user">
                  <span className="flex items-center gap-1.5"><UserCheck className="h-3 w-3" />Tenant User</span>
                </SelectItem>
                <SelectItem value="published_app_account">
                  <span className="flex items-center gap-1.5"><Globe className="h-3 w-3" />Published App Account</span>
                </SelectItem>
                <SelectItem value="embedded_external_user">
                  <span className="flex items-center gap-1.5"><Bot className="h-3 w-3" />Embedded External User</span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {principalType === "tenant_user" && (
            <div className="space-y-2">
              <Label>User</Label>
              <Select value={userId} onValueChange={setUserId}>
                <SelectTrigger className="h-8 w-full">
                  <SelectValue placeholder="Select a user..." />
                </SelectTrigger>
                <SelectContent>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.display_name || u.email || u.id.slice(0, 8)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {principalType === "published_app_account" && (
            <div className="space-y-2">
              <Label>Published App Account ID</Label>
              <Input
                value={publishedAppAccountId}
                onChange={(e) => setPublishedAppAccountId(e.target.value)}
                placeholder="UUID of the published app account"
              />
            </div>
          )}

          {principalType === "embedded_external_user" && (
            <>
              <div className="space-y-2">
                <Label>Embedded Agent</Label>
                <Select value={embeddedAgentId} onValueChange={setEmbeddedAgentId}>
                  <SelectTrigger className="h-8 w-full">
                    <SelectValue placeholder="Select an agent..." />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((a) => (
                      <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>External User ID</Label>
                <Input
                  value={externalUserId}
                  onChange={(e) => setExternalUserId(e.target.value)}
                  placeholder="External user identifier"
                />
              </div>
            </>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !isValid()} className="gap-1.5">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create Assignment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ── Defaults Section ── */

function DefaultsSection({
  publishedApps,
  agents,
  policySets,
}: {
  publishedApps: PublishedApp[]
  agents: Agent[]
  policySets: ResourcePolicySet[]
}) {
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Track defaults in local state so selections persist after API calls
  const [appDefaults, setAppDefaults] = useState<Record<string, string>>({})
  const [agentDefaults, setAgentDefaults] = useState<Record<string, string>>({})

  useEffect(() => {
    const ad: Record<string, string> = {}
    publishedApps.forEach((app) => {
      const val = app.default_policy_set_id
      if (val) ad[app.id] = val
    })
    setAppDefaults(ad)
  }, [publishedApps])

  useEffect(() => {
    const ad: Record<string, string> = {}
    agents.forEach((agent) => {
      const val = agent.default_embed_policy_set_id
      if (val) ad[agent.id] = val
    })
    setAgentDefaults(ad)
  }, [agents])

  const activePolicySets = policySets.filter((ps) => ps.is_active)

  const handleSetAppDefault = async (appId: string, policySetId: string | null) => {
    setSaving(appId)
    setError(null)
    try {
      await resourcePoliciesService.setPublishedAppDefaultPolicy(appId, policySetId)
      if (policySetId) {
        setAppDefaults((prev) => ({ ...prev, [appId]: policySetId }))
      } else {
        setAppDefaults((prev) => {
          const next = { ...prev }
          delete next[appId]
          return next
        })
      }
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(null)
    }
  }

  const handleSetAgentDefault = async (agentId: string, policySetId: string | null) => {
    setSaving(agentId)
    setError(null)
    try {
      await resourcePoliciesService.setEmbeddedAgentDefaultPolicy(agentId, policySetId)
      if (policySetId) {
        setAgentDefaults((prev) => ({ ...prev, [agentId]: policySetId }))
      } else {
        setAgentDefaults((prev) => {
          const next = { ...prev }
          delete next[agentId]
          return next
        })
      }
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Published Apps */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Globe className="h-4 w-4 text-muted-foreground" />
            Published Apps
          </h4>
          {publishedApps.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
              <p className="text-xs text-muted-foreground">No published apps found.</p>
            </div>
          ) : (
            <div className="rounded-xl bg-background overflow-hidden">
              {publishedApps.map((app, i) => (
                <div
                  key={app.id}
                  className={cn(
                    "flex items-center justify-between gap-3 px-4 py-2.5",
                    i < publishedApps.length - 1 && "border-b border-border/30"
                  )}
                >
                  <span className="text-sm font-medium truncate min-w-0">{app.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <Select
                      value={appDefaults[app.id] || "__none__"}
                      onValueChange={(v) => handleSetAppDefault(app.id, v === "__none__" ? null : v)}
                      disabled={saving === app.id}
                    >
                      <SelectTrigger className="w-40 h-7 text-xs">
                        <SelectValue placeholder="No default" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">
                          <span className="text-muted-foreground">No default</span>
                        </SelectItem>
                        {activePolicySets.map((ps) => (
                          <SelectItem key={ps.id} value={ps.id}>{ps.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {saving === app.id && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Embedded Agents */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Bot className="h-4 w-4 text-muted-foreground" />
            Embedded Agents
          </h4>
          {agents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
              <p className="text-xs text-muted-foreground">No agents found.</p>
            </div>
          ) : (
            <div className="rounded-xl bg-background overflow-hidden">
              {agents.map((agent, i) => (
                <div
                  key={agent.id}
                  className={cn(
                    "flex items-center justify-between gap-3 px-4 py-2.5",
                    i < agents.length - 1 && "border-b border-border/30"
                  )}
                >
                  <span className="text-sm font-medium truncate min-w-0">{agent.name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <Select
                      value={agentDefaults[agent.id] || "__none__"}
                      onValueChange={(v) => handleSetAgentDefault(agent.id, v === "__none__" ? null : v)}
                      disabled={saving === agent.id}
                    >
                      <SelectTrigger className="w-40 h-7 text-xs">
                        <SelectValue placeholder="No default" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">
                          <span className="text-muted-foreground">No default</span>
                        </SelectItem>
                        {activePolicySets.map((ps) => (
                          <SelectItem key={ps.id} value={ps.id}>{ps.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {saving === agent.id && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Reusable Delete Dialog ── */

function DeleteDialog({
  open,
  title,
  description,
  onClose,
  onConfirm,
  loading,
  error,
}: {
  open: boolean
  title: string
  description: React.ReactNode
  onClose: () => void
  onConfirm: () => void
  loading: boolean
  error: string | null
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {error && (
          <div className="flex items-start gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            {error}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onConfirm}
            disabled={loading}
            className="gap-1.5"
          >
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
