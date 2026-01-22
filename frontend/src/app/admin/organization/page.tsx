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
  Loader2
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"

export default function OrganizationPage() {
  const { currentTenant } = useTenant()
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [tree, setTree] = useState<OrgUnitTree[]>([])
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null)
  const [members, setMembers] = useState<OrgMember[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isMembersLoading, setIsMembersLoading] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Dialog states
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [isMemberDialogOpen, setIsMemberDialogOpen] = useState(false)
  const [editUnit, setEditUnit] = useState<OrgUnitTree | null>(null)
  const [newUnitData, setNewUnitData] = useState({ name: "", slug: "", type: "dept" as "dept" | "team", parent_id: "" })
  const [newMemberEmail, setNewMemberEmail] = useState("")

  const fetchTree = useCallback(async () => {
    if (!currentTenant) return
    setIsLoading(true)
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
      setIsLoading(false)
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
      fetchTree()
    } catch (error) {
      console.error("Failed to delete unit", error)
    }
  }

  const handleAddMember = async () => {
    // This requires a user ID, we'd typically have a search or input by email
    // For now, let's assume we search for user by email first
    // Since we don't have that service yet, we'll just log it
    console.log("Add member by email:", newMemberEmail, "to", selectedUnitId)
    // Placeholder implementation
    setIsMemberDialogOpen(false)
    setNewMemberEmail("")
  }

  const TreeNode = ({ unit, depth = 0, isLast = false, parentExpanded = true }: { unit: OrgUnitTree; depth?: number; isLast?: boolean; parentExpanded?: boolean }) => {
    const isExpanded = expandedIds.has(unit.id)
    const isSelected = selectedUnitId === unit.id
    const hasChildren = unit.children && unit.children.length > 0

    return (
      <div className="flex flex-col relative">
        {/* Hierarchy line for depth > 0 */}
        {depth > 0 && parentExpanded && (
          <div
            className={cn(
              "absolute top-0 w-px bg-border/60",
              isRTL ? "right-[-12px]" : "left-[-12px]",
              isLast ? "h-3" : "h-full"
            )}
          />
        )}
        {depth > 0 && parentExpanded && (
          <div
            className={cn(
              "absolute top-3 h-px bg-border/60 w-3",
              isRTL ? "right-[-12px]" : "left-[-12px]"
            )}
          />
        )}

        <div
          className={cn(
            "flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer group transition-all duration-200 relative",
            isSelected ? 'bg-primary/10 text-primary font-medium shadow-sm' : 'hover:bg-muted/60 text-muted-foreground hover:text-foreground'
          )}
          style={{
            marginLeft: isRTL ? '0' : `${depth > 0 ? 12 : 0}px`,
            marginRight: isRTL ? `${depth > 0 ? 12 : 0}px` : '0',
            marginTop: depth === 0 ? '4px' : '2px'
          }}
          onClick={() => {
            setSelectedUnitId(unit.id)
            if (hasChildren) toggleExpand(unit.id)
          }}
        >
          {isSelected && (
            <div className={cn(
              "absolute top-1.5 bottom-1.5 w-1 bg-primary rounded-full",
              isRTL ? "-right-1" : "-left-1"
            )} />
          )}

          <div className="flex items-center justify-center size-5 shrink-0">
            {hasChildren ? (
              <div className="hover:bg-muted p-0.5 rounded transition-colors">
                {isExpanded ? <ChevronDown className="size-3.5" /> : (isRTL ? <ChevronLeft className="size-3.5" /> : <ChevronRight className="size-3.5" />)}
              </div>
            ) : (
              <div className="size-3.5" />
            )}
          </div>

          <div className={cn(
            "p-1 rounded-md shrink-0",
            unit.type === "org" ? "bg-blue-100/50 text-blue-600 dark:bg-blue-900/30" :
              unit.type === "dept" ? "bg-green-100/50 text-green-600 dark:bg-green-900/30" :
                "bg-purple-100/50 text-purple-600 dark:bg-purple-900/30"
          )}>
            {unit.type === "org" && <Landmark className="size-3.5" />}
            {unit.type === "dept" && <Building2 className="size-3.5" />}
            {unit.type === "team" && <Users className="size-3.5" />}
          </div>

          <span className="flex-1 truncate text-[13px]">{unit.name}</span>

          <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition-opacity">
            <Button variant="ghost" size="icon" className="size-7 hover:bg-background/80" onClick={(e) => {
              e.stopPropagation()
              setNewUnitData(prev => ({ ...prev, parent_id: unit.id, type: unit.type === "org" ? "dept" : "team" }))
              setIsCreateDialogOpen(true)
            }}>
              <Plus className="size-3.5" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={e => e.stopPropagation()}>
                <Button variant="ghost" size="icon" className="size-7 hover:bg-background/80">
                  <MoreVertical className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align={isRTL ? "start" : "end"} className="w-40">
                <DropdownMenuItem onClick={() => {
                  setEditUnit(unit)
                  setIsEditDialogOpen(true)
                }} className="gap-2">
                  <Edit2 className="size-3.5" /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem className="text-destructive gap-2" onClick={() => handleDeleteUnit(unit.id)}>
                  <Trash2 className="size-3.5" /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        {isExpanded && (
          <div className="flex flex-col">
            {unit.children.map((child, idx) => (
              <TreeNode
                key={child.id}
                unit={child}
                depth={depth + 1}
                isLast={idx === unit.children.length - 1}
                parentExpanded={isExpanded}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  if (!currentTenant) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Please select a tenant from the sidebar to manage organization units.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <CustomBreadcrumb items={[
              { label: "Dashboard", href: "/admin/dashboard" },
              { label: "Organization Units", active: true },
            ]} />
          </div>
        </div>
        <Button size="sm" className="h-9" onClick={() => {
          setNewUnitData({ name: "", slug: "", type: "dept", parent_id: "" })
          setIsCreateDialogOpen(true)
        }}>
          <Plus className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> New Root Unit
        </Button>
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1">
          {/* Hierarchy Tree */}
          <Card className="md:col-span-1 flex flex-col overflow-hidden">
            <CardHeader className="py-4">
              <CardTitle className={cn("text-base", isRTL ? "text-right" : "text-left")}>Hierarchy</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-auto px-2 py-0 pb-4">
              {isLoading ? (
                <div className="space-y-2 p-2">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ) : tree.length === 0 ? (
                <div className={cn("p-4 text-center text-sm text-muted-foreground", isRTL ? "text-right" : "text-left")}>
                  No units created yet.
                </div>
              ) : (
                tree.map(unit => <TreeNode key={unit.id} unit={unit} />)
              )}
            </CardContent>
          </Card>

          {/* Selected Unit Details */}
          <Card className="md:col-span-2 flex flex-col">
            <Tabs defaultValue="members" className="flex-1 flex flex-col" dir={direction}>
              <CardHeader className="py-4 border-b">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 rounded-lg">
                      {tree.find(u => u.id === selectedUnitId)?.type === "org" && <Landmark className="size-5 text-primary" />}
                      {tree.find(u => u.id === selectedUnitId)?.type === "dept" && <Building2 className="size-5 text-primary" />}
                      {tree.find(u => u.id === selectedUnitId)?.type === "team" && <Users className="size-5 text-primary" />}
                    </div>
                    <div>
                      <CardTitle className={cn("text-lg", isRTL ? "text-right" : "text-left")}>
                        {tree.find(u => u.id === selectedUnitId)?.name || "Select a unit"}
                      </CardTitle>
                      <CardDescription className={isRTL ? "text-right" : "text-left"}>
                        {tree.find(u => u.id === selectedUnitId)?.slug || "No description"}
                      </CardDescription>
                    </div>
                  </div>
                  <TabsList>
                    <TabsTrigger value="members">Members</TabsTrigger>
                    <TabsTrigger value="settings">Settings</TabsTrigger>
                  </TabsList>
                </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden p-0">
                <TabsContent value="members" className="h-full m-0 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className={cn("text-sm font-medium", isRTL ? "text-right" : "text-left")}>Unit Members</h3>
                    <Button variant="outline" size="sm" onClick={() => setIsMemberDialogOpen(true)}>
                      <UserPlus className={cn("size-4", isRTL ? "ml-2" : "mr-2")} /> Add Member
                    </Button>
                  </div>
                  {isMembersLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : members.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground border-2 border-dashed rounded-lg">
                      No members in this unit.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>User</TableHead>
                          <TableHead className={isRTL ? "text-right" : "text-left"}>Joined</TableHead>
                          <TableHead className={isRTL ? "text-left" : "text-right"}>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {members.map(member => (
                          <TableRow key={member.membership_id}>
                            <TableCell className={isRTL ? "text-right" : "text-left"}>
                              <div>
                                <div className="font-medium">{member.full_name || "Unknown User"}</div>
                                <div className="text-xs text-muted-foreground">{member.email}</div>
                              </div>
                            </TableCell>
                            <TableCell className={cn("text-sm", isRTL ? "text-right" : "text-left")}>
                              {new Date(member.joined_at).toLocaleDateString()}
                            </TableCell>
                            <TableCell className={isRTL ? "text-left" : "text-right"}>
                              <Button variant="ghost" size="icon" onClick={() => {
                                if (confirm("Remove user from this unit?")) {
                                  orgUnitsService.removeMember(currentTenant.slug, member.membership_id)
                                    .then(fetchMembers)
                                    .catch(console.error)
                                }
                              }}>
                                <Trash2 className="size-4 text-destructive" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </TabsContent>
                <TabsContent value="settings" className="h-full m-0 p-6" dir={direction}>
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label className={isRTL ? "text-right block" : "text-left block"}>Unit ID</Label>
                      <Input value={selectedUnitId || ""} disabled className={isRTL ? "text-right" : "text-left"} />
                    </div>
                    <div className="space-y-2">
                      <Label className={isRTL ? "text-right block" : "text-left block"}>Slug (Namespace)</Label>
                      <Input value={tree.find(u => u.id === selectedUnitId)?.slug || ""} disabled className={isRTL ? "text-right" : "text-left"} />
                    </div>
                    <div className={cn("pt-4 flex gap-2", isRTL ? "justify-start" : "justify-end")}>
                      <Button variant="outline" onClick={() => {
                        setEditUnit(tree.find(u => u.id === selectedUnitId) || null)
                        setIsEditDialogOpen(true)
                      }}>Edit Basic Details</Button>
                      <Button variant="destructive" onClick={() => handleDeleteUnit(selectedUnitId!)}>Delete Unit</Button>
                    </div>
                  </div>
                </TabsContent>
              </CardContent>
            </Tabs>
          </Card>
        </div>

        {/* Create Dialog */}
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Organization Unit</DialogTitle>
              <DialogDescription>
                Add a new department or team to your hierarchy.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Unit Name</Label>
                <Input
                  id="name"
                  placeholder="Engineering"
                  value={newUnitData.name}
                  onChange={e => setNewUnitData({ ...newUnitData, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="slug">Slug (URL friendly)</Label>
                <Input
                  id="slug"
                  placeholder="engineering"
                  value={newUnitData.slug}
                  onChange={e => setNewUnitData({ ...newUnitData, slug: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">Type</Label>
                <select
                  id="type"
                  className="w-full h-10 px-3 rounded-md border border-input bg-background"
                  value={newUnitData.type}
                  onChange={e => setNewUnitData({ ...newUnitData, type: e.target.value as any })}
                >
                  <option value="dept">Department</option>
                  <option value="team">Team</option>
                </select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleCreateUnit} disabled={!newUnitData.name || !newUnitData.slug}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Edit Dialog */}
        <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit Organization Unit</DialogTitle>
            </DialogHeader>
            {editUnit && (
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-name">Unit Name</Label>
                  <Input
                    id="edit-name"
                    value={editUnit.name}
                    onChange={e => setEditUnit({ ...editUnit, name: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-slug">Slug</Label>
                  <Input
                    id="edit-slug"
                    value={editUnit.slug}
                    onChange={e => setEditUnit({ ...editUnit, slug: e.target.value })}
                  />
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleUpdateUnit}>Save Changes</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Add Member Dialog */}
        <Dialog open={isMemberDialogOpen} onOpenChange={setIsMemberDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Member to Unit</DialogTitle>
              <DialogDescription>
                Invite a user to join this organization unit.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="member-email">User Email</Label>
                <Input
                  id="member-email"
                  type="email"
                  placeholder="user@example.com"
                  value={newMemberEmail}
                  onChange={e => setNewMemberEmail(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsMemberDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleAddMember} disabled={!newMemberEmail}>Invite User</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
