"use client"

import React, { useState, useEffect, useCallback } from "react"
import { useTenant } from "@/contexts/TenantContext"
import { useDirection } from "@/components/direction-provider"
import { orgUnitsService, OrgUnitTree, OrgMember } from "@/services/org-units"
import {
  Plus,
  Trash2,
  Edit2,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  Building2,
  Landmark,
  Users,
  UserPlus,
  MoreVertical,
  Settings,
  Mail,
  Calendar,
  FolderTree,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

const UNIT_TYPE_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  org: { icon: Landmark, label: "Organization", color: "bg-violet-500" },
  dept: { icon: Building2, label: "Department", color: "bg-blue-500" },
  team: { icon: Users, label: "Team", color: "bg-emerald-500" },
}

function findUnitInTree(nodes: OrgUnitTree[], id: string): OrgUnitTree | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = findUnitInTree(node.children, id)
    if (found) return found
  }
  return null
}

function flattenTree(nodes: OrgUnitTree[]): OrgUnitTree[] {
  const result: OrgUnitTree[] = []
  for (const node of nodes) {
    result.push(node)
    result.push(...flattenTree(node.children))
  }
  return result
}

/* ------------------------------------------------------------------ */
/*  Skeleton loaders                                                  */
/* ------------------------------------------------------------------ */

function TreeSkeleton() {
  return (
    <div className="space-y-1 p-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2 px-2 py-1.5" style={{ paddingLeft: `${8 + i * 12}px` }}>
          <Skeleton className="h-4 w-4 rounded shrink-0" />
          <Skeleton className="h-3.5 w-3.5 rounded shrink-0" />
          <Skeleton className={cn("h-3.5 rounded", i % 2 === 0 ? "w-24" : "w-16")} />
        </div>
      ))}
    </div>
  )
}

function MemberRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-border/30 last:border-0">
      <Skeleton className="h-8 w-8 rounded-full shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-3.5 w-32" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-3 w-16 hidden md:block" />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Field row for settings                                            */
/* ------------------------------------------------------------------ */

function FieldRow({
  label,
  value,
  mono = false,
  isRTL = false,
}: {
  label: string
  value: string
  mono?: boolean
  isRTL?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2.5 px-1 border-b border-border/30 last:border-0">
      <span className={cn(
        "text-xs font-medium text-muted-foreground/60",
        isRTL ? "text-right" : "text-left"
      )}>
        {label}
      </span>
      <span className={cn(
        "text-sm text-foreground truncate max-w-[60%]",
        mono && "font-mono text-xs",
        isRTL ? "text-left" : "text-right"
      )}>
        {value || "--"}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main page                                                         */
/* ------------------------------------------------------------------ */

export default function OrganizationPage() {
  const { currentTenant } = useTenant()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [tree, setTree] = useState<OrgUnitTree[]>([])
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null)
  const [members, setMembers] = useState<OrgMember[]>([])
  const [isTreeLoading, setIsTreeLoading] = useState(true)
  const [isMembersLoading, setIsMembersLoading] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Dialog states
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [isMemberDialogOpen, setIsMemberDialogOpen] = useState(false)
  const [editUnit, setEditUnit] = useState<OrgUnitTree | null>(null)
  const [newUnitData, setNewUnitData] = useState({ name: "", slug: "", type: "dept" as "dept" | "team", parent_id: "" })
  const [newMemberEmail, setNewMemberEmail] = useState("")

  /* ---- Data fetching ---- */

  const fetchTree = useCallback(async () => {
    if (!currentTenant) return
    setIsTreeLoading(true)
    try {
      const data = await orgUnitsService.getOrgUnitTree(currentTenant.slug)
      setTree(data)
      if (data.length > 0 && !selectedUnitId) {
        setSelectedUnitId(data[0].id)
        setExpandedIds(new Set([data[0].id]))
      }
    } catch (error) {
      console.error("Failed to fetch tree", error)
    } finally {
      setIsTreeLoading(false)
    }
  }, [currentTenant, selectedUnitId])

  const fetchMembers = useCallback(async () => {
    if (!currentTenant || !selectedUnitId) return
    setIsMembersLoading(true)
    try {
      const data = await orgUnitsService.listMembers(currentTenant.slug, selectedUnitId)
      setMembers(data.members)
    } catch (error) {
      console.error("Failed to fetch members", error)
    } finally {
      setIsMembersLoading(false)
    }
  }, [currentTenant, selectedUnitId])

  useEffect(() => {
    fetchTree()
  }, [currentTenant, fetchTree])

  useEffect(() => {
    fetchMembers()
  }, [selectedUnitId, fetchMembers])

  /* ---- Handlers ---- */

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleCreateUnit = async () => {
    if (!currentTenant) return
    try {
      await orgUnitsService.createOrgUnit(currentTenant.slug, newUnitData)
      setIsCreateDialogOpen(false)
      setNewUnitData({ name: "", slug: "", type: "dept", parent_id: "" })
      fetchTree()
    } catch (error) {
      console.error("Failed to create unit", error)
    }
  }

  const handleUpdateUnit = async () => {
    if (!currentTenant || !editUnit) return
    try {
      await orgUnitsService.updateOrgUnit(currentTenant.slug, editUnit.id, { name: editUnit.name, slug: editUnit.slug })
      setIsEditDialogOpen(false)
      setEditUnit(null)
      fetchTree()
    } catch (error) {
      console.error("Failed to update unit", error)
    }
  }

  const handleDeleteUnit = async (id: string) => {
    if (!currentTenant || !confirm("Are you sure you want to delete this unit?")) return
    try {
      await orgUnitsService.deleteOrgUnit(currentTenant.slug, id)
      if (selectedUnitId === id) setSelectedUnitId(null)
      fetchTree()
    } catch (error) {
      console.error("Failed to delete unit", error)
    }
  }

  const handleAddMember = async () => {
    // Placeholder: would search user by email, then add by user_id
    console.log("Add member by email:", newMemberEmail, "to", selectedUnitId)
    setIsMemberDialogOpen(false)
    setNewMemberEmail("")
  }

  /* ---- Derived ---- */

  const selectedUnit = findUnitInTree(tree, selectedUnitId || "")
  const unitConfig = selectedUnit ? UNIT_TYPE_CONFIG[selectedUnit.type] || UNIT_TYPE_CONFIG.team : null

  /* ---- Tree node component ---- */

  const TreeNode = ({
    unit,
    depth = 0,
  }: {
    unit: OrgUnitTree
    depth?: number
  }) => {
    const isExpanded = expandedIds.has(unit.id)
    const isSelected = selectedUnitId === unit.id
    const hasChildren = unit.children && unit.children.length > 0
    const config = UNIT_TYPE_CONFIG[unit.type] || UNIT_TYPE_CONFIG.team
    const UnitIcon = config.icon

    return (
      <div className="flex flex-col">
        <div
          className={cn(
            "group flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition-colors relative",
            isSelected
              ? "bg-muted/60 text-foreground font-medium"
              : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
          )}
          style={{
            [isRTL ? "paddingRight" : "paddingLeft"]: `${8 + depth * 16}px`,
          }}
          onClick={() => {
            setSelectedUnitId(unit.id)
            if (hasChildren) toggleExpand(unit.id)
          }}
        >
          {/* Selection indicator */}
          {isSelected && (
            <div
              className={cn(
                "absolute top-1.5 bottom-1.5 w-0.5 bg-foreground/70 rounded-full",
                isRTL ? "right-0.5" : "left-0.5"
              )}
            />
          )}

          {/* Expand/collapse chevron */}
          <div className="flex items-center justify-center size-4 shrink-0">
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="size-3 text-muted-foreground/60" />
              ) : isRTL ? (
                <ChevronLeft className="size-3 text-muted-foreground/60" />
              ) : (
                <ChevronRight className="size-3 text-muted-foreground/60" />
              )
            ) : (
              <span className="size-3" />
            )}
          </div>

          {/* Unit icon */}
          <div className={cn(
            "flex items-center justify-center size-5 rounded shrink-0",
            isSelected ? "text-foreground/80" : "text-muted-foreground/60"
          )}>
            <UnitIcon className="size-3.5" />
          </div>

          {/* Name */}
          <span className="flex-1 truncate text-[13px] leading-tight">
            {unit.name}
          </span>

          {/* Hover actions */}
          <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="size-6 hover:bg-background/80"
              onClick={(e) => {
                e.stopPropagation()
                setNewUnitData(prev => ({
                  ...prev,
                  parent_id: unit.id,
                  type: unit.type === "org" ? "dept" : "team",
                }))
                setIsCreateDialogOpen(true)
              }}
            >
              <Plus className="size-3" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                <Button variant="ghost" size="icon" className="size-6 hover:bg-background/80">
                  <MoreVertical className="size-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align={isRTL ? "start" : "end"} className="w-40">
                <DropdownMenuItem
                  onClick={() => {
                    setEditUnit(unit)
                    setIsEditDialogOpen(true)
                  }}
                  className="gap-2 text-xs"
                >
                  <Edit2 className="size-3.5" /> Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive gap-2 text-xs"
                  onClick={() => handleDeleteUnit(unit.id)}
                >
                  <Trash2 className="size-3.5" /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Children */}
        {isExpanded && hasChildren && (
          <div className="flex flex-col">
            {unit.children.map((child) => (
              <TreeNode key={child.id} unit={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    )
  }

  /* ---- No tenant guard ---- */

  if (!currentTenant) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center bg-background">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
          <Building2 className="h-6 w-6 text-muted-foreground/40" />
        </div>
        <p className="text-sm text-muted-foreground/70">
          Select a tenant from the sidebar to manage organization.
        </p>
      </div>
    )
  }

  /* ---- Render ---- */

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-background" dir={direction}>
      {/* Header */}
      <header className="h-12 shrink-0 bg-background px-4 flex items-center justify-between">
        <CustomBreadcrumb
          items={[
            { label: "Security & Org", href: "/admin/organization" },
            { label: "Organization", active: true },
          ]}
        />
        <Button
          size="sm"
          className="h-8 gap-1.5"
          onClick={() => {
            setNewUnitData({ name: "", slug: "", type: "dept", parent_id: "" })
            setIsCreateDialogOpen(true)
          }}
        >
          <Plus className="h-3.5 w-3.5" />
          New Unit
        </Button>
      </header>

      {/* Body: sidebar + detail */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Tree sidebar */}
        <aside
          className={cn(
            "w-64 shrink-0 overflow-y-auto bg-background",
            isRTL ? "border-l border-border/40" : "border-r border-border/40"
          )}
        >
          <div className="px-3 pt-3 pb-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/50">
              Hierarchy
            </span>
          </div>

          {isTreeLoading && tree.length === 0 ? (
            <TreeSkeleton />
          ) : tree.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-3">
                <FolderTree className="h-5 w-5 text-muted-foreground/40" />
              </div>
              <p className="text-xs font-medium text-foreground mb-0.5">No units yet</p>
              <p className="text-xs text-muted-foreground/60 mb-3">
                Create your first organization unit.
              </p>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                onClick={() => setIsCreateDialogOpen(true)}
              >
                <Plus className="h-3 w-3" />
                Create Unit
              </Button>
            </div>
          ) : (
            <div className="px-1 pb-3 space-y-0.5">
              {tree.map((unit) => (
                <TreeNode key={unit.id} unit={unit} />
              ))}
            </div>
          )}
        </aside>

        {/* Detail panel */}
        <main className="flex-1 min-w-0 overflow-y-auto">
          {!selectedUnit ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-4">
                <Building2 className="h-6 w-6 text-muted-foreground/40" />
              </div>
              <h3 className="text-sm font-medium text-foreground mb-1">Select a unit</h3>
              <p className="text-xs text-muted-foreground/60 max-w-[260px]">
                Choose an organization unit from the tree to view members and settings.
              </p>
            </div>
          ) : (
            <div className="flex flex-col h-full">
              {/* Tabs Wrapper with Unit Info */}
              <Tabs defaultValue="members" className="flex-1 flex flex-col min-h-0" dir={direction}>
                <div className="shrink-0 border-b border-border/40 px-6 py-4 flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={cn(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-muted-foreground/70"
                    )}>
                      {unitConfig && <unitConfig.icon className="h-4 w-4" />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h2 className="text-sm font-medium text-foreground truncate">
                          {selectedUnit.name}
                        </h2>
                        <span className="flex items-center gap-1.5 shrink-0">
                          <span className={cn("h-1.5 w-1.5 rounded-full", unitConfig?.color || "bg-zinc-400")} />
                          <span className="text-xs text-muted-foreground/70">
                            {unitConfig?.label || selectedUnit.type}
                          </span>
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground/50 font-mono truncate mt-0.5">
                        {selectedUnit.slug}
                      </p>
                    </div>
                  </div>

                  <TabsList>
                    <TabsTrigger value="members">Members</TabsTrigger>
                    <TabsTrigger value="settings">Settings</TabsTrigger>
                  </TabsList>
                </div>

                {/* Members tab */}
                <TabsContent value="members" className="flex-1 m-0 overflow-y-auto">
                  <div className="px-6 py-4">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className={cn("text-sm font-medium text-foreground", isRTL ? "text-right" : "text-left")}>
                          Unit Members
                        </h3>
                        <p className="text-xs text-muted-foreground/60 mt-0.5">
                          Members inherit permissions based on unit scope.
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 gap-1.5 text-xs"
                        onClick={() => setIsMemberDialogOpen(true)}
                        disabled={!selectedUnitId}
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                        Add Member
                      </Button>
                    </div>

                    {isMembersLoading ? (
                      <div className="rounded-xl border border-border/50 overflow-hidden bg-card shadow-xs">
                        {Array.from({ length: 3 }).map((_, i) => (
                          <MemberRowSkeleton key={i} />
                        ))}
                      </div>
                    ) : members.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-16 text-center">
                        <div className="flex h-12 w-12 items-center justify-center rounded-xl border-2 border-dashed border-border/60 mb-3">
                          <Users className="h-5 w-5 text-muted-foreground/40" />
                        </div>
                        <p className="text-xs font-medium text-foreground mb-0.5">No members</p>
                        <p className="text-xs text-muted-foreground/60 max-w-[220px]">
                          Add members to this unit to grant scoped permissions.
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-border/50 overflow-hidden bg-card shadow-xs divide-y divide-border/30">
                        {members.map((member) => (
                          <div
                            key={member.membership_id}
                            className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/30"
                          >
                            {/* Avatar */}
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted/50 text-xs font-medium text-muted-foreground">
                              {(member.full_name || member.email || "?")
                                .charAt(0)
                                .toUpperCase()}
                            </div>

                            {/* Name + email */}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate leading-tight">
                                {member.full_name || "Unknown User"}
                              </p>
                              <p className="text-xs text-muted-foreground/50 truncate flex items-center gap-1 mt-0.5">
                                <Mail className="h-3 w-3 shrink-0" />
                                {member.email}
                              </p>
                            </div>

                            {/* Joined date */}
                            <span className="hidden md:flex items-center gap-1 text-xs text-muted-foreground/50 shrink-0">
                              <Calendar className="h-3 w-3" />
                              {new Date(member.joined_at).toLocaleDateString()}
                            </span>

                            {/* Remove button */}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                              onClick={() => {
                                if (confirm("Remove user from this unit?")) {
                                  orgUnitsService
                                    .removeMember(currentTenant.slug, member.membership_id)
                                    .then(fetchMembers)
                                    .catch(console.error)
                                }
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </TabsContent>

                {/* Settings tab */}
                <TabsContent value="settings" className="flex-1 m-0 overflow-y-auto" dir={direction}>
                  <div className="px-6 py-4 space-y-6">
                    {/* Unit details section */}
                    <div>
                      <h3 className={cn("text-sm font-medium text-foreground mb-0.5", isRTL ? "text-right" : "text-left")}>
                        Unit Details
                      </h3>
                      <p className="text-xs text-muted-foreground/60 mb-3">
                        Basic information about this organization unit.
                      </p>
                      <div className="rounded-xl border border-border/50 px-4">
                        <FieldRow label="Unit ID" value={selectedUnitId || ""} mono isRTL={isRTL} />
                        <FieldRow label="Slug (Namespace)" value={selectedUnit.slug} mono isRTL={isRTL} />
                        <FieldRow label="Type" value={unitConfig?.label || selectedUnit.type} isRTL={isRTL} />
                        <FieldRow
                          label="Children"
                          value={`${selectedUnit.children?.length || 0} sub-units`}
                          isRTL={isRTL}
                        />
                      </div>
                    </div>

                    {/* Scope info */}
                    <div className="rounded-xl border border-border/50 bg-muted/20 shadow-xs p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <Settings className="h-3.5 w-3.5 text-muted-foreground/60" />
                        <span className="text-xs font-medium text-foreground">
                          Scope-aware permissions
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground/60 leading-relaxed">
                        Roles assigned to this unit apply to child units unless overridden.
                        Members inherit access based on their position in the hierarchy.
                      </p>
                    </div>

                    {/* Actions */}
                    <div className={cn("flex items-center gap-2 pt-1", isRTL ? "justify-start" : "justify-end")}>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1.5 text-xs"
                        onClick={() => {
                          if (!selectedUnitId) return
                          const unit = findUnitInTree(tree, selectedUnitId)
                          if (!unit) return
                          setEditUnit(unit)
                          setIsEditDialogOpen(true)
                        }}
                        disabled={!selectedUnitId}
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                        Edit Details
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1.5 text-xs text-destructive hover:text-destructive hover:bg-destructive/10 border-destructive/30"
                        onClick={() => handleDeleteUnit(selectedUnitId!)}
                        disabled={!selectedUnitId}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete Unit
                      </Button>
                    </div>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </main>
      </div>

      {/* ---- Dialogs ---- */}

      {/* Create unit dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Create Organization Unit</DialogTitle>
            <DialogDescription>
              Add a new department or team to your hierarchy.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="create-name" className="text-xs font-medium text-muted-foreground">
                Unit Name
              </Label>
              <Input
                id="create-name"
                placeholder="Engineering"
                value={newUnitData.name}
                onChange={(e) => setNewUnitData({ ...newUnitData, name: e.target.value })}
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-slug" className="text-xs font-medium text-muted-foreground">
                Slug (URL friendly)
              </Label>
              <Input
                id="create-slug"
                placeholder="engineering"
                value={newUnitData.slug}
                onChange={(e) => setNewUnitData({ ...newUnitData, slug: e.target.value })}
                className="h-9 font-mono text-sm"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-medium text-muted-foreground">
                Type
              </Label>
              <Select
                value={newUnitData.type}
                onValueChange={(value) =>
                  setNewUnitData({ ...newUnitData, type: value as "dept" | "team" })
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dept">Department</SelectItem>
                  <SelectItem value="team">Team</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {newUnitData.parent_id && (
              <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
                <p className="text-xs text-muted-foreground/60">
                  <span className="font-medium text-muted-foreground">Parent:</span>{" "}
                  {findUnitInTree(tree, newUnitData.parent_id)?.name || newUnitData.parent_id}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateUnit}
              disabled={!newUnitData.name || !newUnitData.slug}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit unit dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Edit Organization Unit</DialogTitle>
            <DialogDescription>
              Update the name or slug of this unit.
            </DialogDescription>
          </DialogHeader>
          {editUnit ? (
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="edit-name" className="text-xs font-medium text-muted-foreground">
                  Unit Name
                </Label>
                <Input
                  id="edit-name"
                  value={editUnit.name}
                  onChange={(e) => setEditUnit({ ...editUnit, name: e.target.value })}
                  className="h-9"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-slug" className="text-xs font-medium text-muted-foreground">
                  Slug
                </Label>
                <Input
                  id="edit-slug"
                  value={editUnit.slug}
                  onChange={(e) => setEditUnit({ ...editUnit, slug: e.target.value })}
                  className="h-9 font-mono text-sm"
                />
              </div>
            </div>
          ) : (
            <div className="py-6 text-sm text-muted-foreground/60 text-center">
              Select an organization unit to edit.
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdateUnit} disabled={!editUnit}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add member dialog */}
      <Dialog open={isMemberDialogOpen} onOpenChange={setIsMemberDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>Add Member</DialogTitle>
            <DialogDescription>
              Invite a user to join this organization unit.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="member-email" className="text-xs font-medium text-muted-foreground">
                User Email
              </Label>
              <Input
                id="member-email"
                type="email"
                placeholder="user@example.com"
                value={newMemberEmail}
                onChange={(e) => setNewMemberEmail(e.target.value)}
                className="h-9"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsMemberDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddMember} disabled={!newMemberEmail}>
              Invite User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
