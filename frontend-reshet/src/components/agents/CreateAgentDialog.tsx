"use client"

import { useEffect, useState } from "react"
import { Bot, Loader2, Save } from "lucide-react"
import { useRouter } from "next/navigation"

import { buildDefaultAgentGraph } from "@/components/agent-builder/default-graph"
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
import { agentService } from "@/services"

interface CreateAgentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateAgentDialog({ open, onOpenChange }: CreateAgentDialogProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  useEffect(() => {
    if (!open) {
      setIsLoading(false)
      setError(null)
      setName("")
      setDescription("")
    }
  }, [open])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return

    try {
      setIsLoading(true)
      setError(null)
      const newAgent = await agentService.createAgent({
        name: name.trim(),
        description: description.trim(),
        status: "draft",
        graph_definition: buildDefaultAgentGraph(),
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
          <div className="space-y-2">
            <Label htmlFor="create-agent-name">Agent Name</Label>
            <Input
              id="create-agent-name"
              placeholder="Research Assistant"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={isLoading}
              required
            />
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
            <Button type="submit" disabled={isLoading || !name.trim()}>
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
