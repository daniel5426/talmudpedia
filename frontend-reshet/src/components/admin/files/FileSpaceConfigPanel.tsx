"use client"

import { useState } from "react"
import type { Agent, FileAccessMode, FileSpace } from "@/services"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Trash2 } from "lucide-react"

interface FileSpaceConfigPanelProps {
  space: FileSpace | null
  links: { agent_id: string; access_mode: FileAccessMode }[]
  agents: Agent[]
  onLinkAgent: (agentId: string, mode: FileAccessMode) => void
  onUnlinkAgent: (agentId: string) => void
}

export function FileSpaceConfigPanel({
  space,
  links,
  agents,
  onLinkAgent,
  onUnlinkAgent,
}: FileSpaceConfigPanelProps) {
  const [activeTab, setActiveTab] = useState("general")
  const [selectedAgentId, setSelectedAgentId] = useState<string>("")
  const [selectedAccessMode, setSelectedAccessMode] = useState<FileAccessMode>("read")

  const availableAgents = agents.filter((agent) => !links.some((link) => link.agent_id === agent.id))

  const handleCreateLink = () => {
    if (!selectedAgentId) return
    onLinkAgent(selectedAgentId, selectedAccessMode)
    setSelectedAgentId("")
    setSelectedAccessMode("read")
  }

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-background [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-border">
      <div className="mx-auto w-full max-w-5xl px-6 py-12 md:px-12">
        <div className="mb-12 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-medium tracking-tight">Configuration Profile</h2>
            <p className="mt-1 text-sm text-muted-foreground/80">Properties, metadata, and connected workflows.</p>
          </div>
        </div>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-8">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="workflows">Workflows</TabsTrigger>
          </TabsList>

          <TabsContent value="general" className="m-0">
            <div className="grid grid-cols-1 gap-x-5 gap-y-12 lg:grid-cols-2">
              <div className="space-y-6">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">01</span> Identity
                </h3>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60">Display Name</Label>
                  <div className="flex h-[38px] w-full items-center rounded-md border border-border/40 bg-transparent px-3">
                    <span className="text-sm">{space?.name || "File Space"}</span>
                  </div>
                </div>

                <div className="group relative pt-2">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60">Description</Label>
                  <div className="flex min-h-[76px] w-full  rounded-md border border-border/40 bg-transparent p-3">
                    <span className="text-sm">{space?.description || "No description provided."}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-6">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">02</span> System Let
                </h3>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60">ID</Label>
                  <div className="flex h-[38px] w-full items-center rounded-md border border-border/40 bg-transparent px-3 font-mono">
                    <span className="text-sm">{space?.id || "—"}</span>
                  </div>
                </div>

                <div className="group relative">
                  <Label className="mb-2 block text-xs font-medium text-muted-foreground/60">Status</Label>
                  <div className="flex h-[38px] w-full items-center gap-2 rounded-md border border-border/40 bg-transparent px-3">
                    <span className="text-sm capitalize">{space?.status || "—"}</span>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="workflows" className="m-0">
             <div className="space-y-6 max-w-2xl">
                <h3 className="flex items-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  <span className="mr-3 text-primary">03</span> Connected Workflows
                </h3>
                <p className="text-sm text-muted-foreground">
                  Link workflows to this file space to grant them direct filesystem access to these files during execution.
                </p>

                <div className="mt-6 space-y-4">
                  {links.length === 0 ? (
                    <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                      No connected workflows.
                    </div>
                  ) : (
                    links.map((link) => {
                      const agent = agents.find((a) => a.id === link.agent_id)
                      return (
                        <div key={link.agent_id} className="flex items-center justify-between gap-4 rounded-md border border-border/40 bg-transparent p-3">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-foreground">{agent?.name || link.agent_id}</div>
                            <div className="text-xs text-muted-foreground truncate font-mono mt-0.5">{link.agent_id}</div>
                          </div>
                          <Badge variant="outline" className="shrink-0">{link.access_mode}</Badge>
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive shrink-0"
                            onClick={() => onUnlinkAgent(link.agent_id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      )
                    })
                  )}
                </div>

                <div className="mt-8 rounded-md border border-border/40 p-4">
                  <h4 className="mb-4 text-sm font-medium">Link New Workflow</h4>
                  <div className="flex items-end gap-3">
                    <div className="flex-1 space-y-2">
                       <Label className="text-xs">Workflow</Label>
                       <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                        <SelectTrigger className="h-[38px]">
                          <SelectValue placeholder="Select workflow..." />
                        </SelectTrigger>
                        <SelectContent>
                          {availableAgents.map((agent) => (
                            <SelectItem key={agent.id} value={agent.id}>{agent.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="w-[140px] space-y-2">
                       <Label className="text-xs">Access Mode</Label>
                       <Select value={selectedAccessMode} onValueChange={(val) => setSelectedAccessMode(val as FileAccessMode)}>
                        <SelectTrigger className="h-[38px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="read">read</SelectItem>
                          <SelectItem value="read_write">read_write</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <Button onClick={handleCreateLink} disabled={!selectedAgentId} className="h-[38px]">
                      Link
                    </Button>
                  </div>
                </div>
             </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
