"use client"

import { useEffect, useState } from "react"
import { Bot, Info, Loader2, Save } from "lucide-react"
import { useRouter } from "next/navigation"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { agentService } from "@/services"
import { buildDefaultEndOutputBindings, buildDefaultEndOutputSchema } from "@/components/agent-builder/graph-contract"

const STARTER_GRAPH = {
  spec_version: "3.0",
  nodes: [
    {
      id: "start",
      type: "start",
      position: { x: 0, y: 0 },
      config: {},
    },
    {
      id: "end",
      type: "end",
      position: { x: 240, y: 0 },
      config: {
        output_schema: buildDefaultEndOutputSchema(),
        output_bindings: buildDefaultEndOutputBindings(),
      },
    },
  ],
  edges: [
    {
      id: "e1",
      source: "start",
      target: "end",
      type: "control",
    },
  ],
}

interface CreateAgentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function slugify(value: string) {
  return value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "")
}

export function CreateAgentDialog({ open, onOpenChange }: CreateAgentDialogProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [slug, setSlug] = useState("")
  const [description, setDescription] = useState("")
  const [isSlugInfoOpen, setIsSlugInfoOpen] = useState(false)

  useEffect(() => {
    if (!open) {
      setIsLoading(false)
      setError(null)
      setName("")
      setSlug("")
      setDescription("")
      setIsSlugInfoOpen(false)
    }
  }, [open])

  const handleNameChange = (value: string) => {
    setName(value)
    if (!slug || slug === slugify(name)) {
      setSlug(slugify(value))
    }
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name || !slug) return

    try {
      setIsLoading(true)
      setError(null)
      const newAgent = await agentService.createAgent({
        name,
        slug,
        description,
        status: "draft",
        graph_definition: STARTER_GRAPH,
      })
      onOpenChange(false)
      router.push(`/admin/agents/${newAgent.id}/builder`)
    } catch (err: any) {
      console.error("Failed to create agent:", err)
      setError(err.message || "Failed to create agent. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Bot className="h-5 w-5" />
            </span>
            Create New Agent
          </DialogTitle>
          <DialogDescription>
            Set the agent identity here. The graph builder opens immediately after creation.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid gap-4 md:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-2">
              <Label htmlFor="create-agent-name">Agent Name</Label>
              <Input
                id="create-agent-name"
                placeholder="Research Assistant"
                value={name}
                onChange={(event) => handleNameChange(event.target.value)}
                disabled={isLoading}
                required
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label htmlFor="create-agent-slug">Slug</Label>
                <Tooltip open={isSlugInfoOpen} onOpenChange={setIsSlugInfoOpen}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label="Slug format information"
                      className="inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => setIsSlugInfoOpen((current) => !current)}
                    >
                      <Info className="h-3.5 w-3.5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" sideOffset={6} className="max-w-56">
                    Stable API identifier. Keep it lowercase and URL-safe.
                  </TooltipContent>
                </Tooltip>
              </div>
              <Input
                id="create-agent-slug"
                placeholder="research-assistant"
                value={slug}
                onChange={(event) => {
                  setSlug(slugify(event.target.value))
                  setError(null)
                }}
                disabled={isLoading}
                className={error?.toLowerCase().includes("slug") ? "border-destructive" : undefined}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="create-agent-description">Description</Label>
            <Textarea
              id="create-agent-description"
              placeholder="Describe what this agent is responsible for."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-28 resize-none"
              disabled={isLoading}
            />
          </div>
          {error && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading || !name || !slug}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Create & Open Builder
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
