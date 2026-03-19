"use client"

import { useCallback, useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Loader2, Save, FileDown } from "lucide-react"
import { promptsService } from "@/services/prompts"
import type { PromptRecord } from "@/services/prompts"

interface PromptModalProps {
  promptId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called when user clicks "Fill" – caller should replace the mention with raw content. */
  onFill?: (promptId: string, content: string) => void
}

export function PromptModal({
  promptId,
  open,
  onOpenChange,
  onFill,
}: PromptModalProps) {
  const [prompt, setPrompt] = useState<PromptRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Editable fields
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editContent, setEditContent] = useState("")
  const [dirty, setDirty] = useState(false)

  // Load prompt data when the modal opens
  useEffect(() => {
    if (!open || !promptId) {
      setPrompt(null)
      setDirty(false)
      return
    }
    setLoading(true)
    setError(null)
    promptsService
      .getPrompt(promptId)
      .then((p) => {
        setPrompt(p)
        setEditName(p.name)
        setEditDescription(p.description || "")
        setEditContent(p.content)
        setDirty(false)
      })
      .catch((err) => setError(String(err?.message || err)))
      .finally(() => setLoading(false))
  }, [open, promptId])

  const handleSave = useCallback(async () => {
    if (!prompt) return
    setSaving(true)
    setError(null)
    try {
      const updated = await promptsService.updatePrompt(prompt.id, {
        name: editName !== prompt.name ? editName : undefined,
        description: editDescription !== (prompt.description || "") ? editDescription : undefined,
        content: editContent !== prompt.content ? editContent : undefined,
      })
      setPrompt(updated)
      setEditName(updated.name)
      setEditDescription(updated.description || "")
      setEditContent(updated.content)
      setDirty(false)
    } catch (err: any) {
      setError(String(err?.message || err))
    } finally {
      setSaving(false)
    }
  }, [prompt, editName, editDescription, editContent])

  const handleFill = useCallback(async () => {
    if (!promptId) return
    // Always fetch latest content from backend, not stale cache
    try {
      const latest = await promptsService.getPrompt(promptId)
      onFill?.(promptId, latest.content)
      onOpenChange(false)
    } catch (err: any) {
      setError(String(err?.message || err))
    }
  }, [promptId, onFill, onOpenChange])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {prompt ? prompt.name : "Prompt"}
          </DialogTitle>
          <DialogDescription>
            {prompt
              ? `Version ${prompt.version} · ${prompt.scope} · ${prompt.status}`
              : "Loading prompt..."}
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {!loading && prompt && (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Name</Label>
              <Input
                value={editName}
                onChange={(e) => {
                  setEditName(e.target.value)
                  setDirty(true)
                }}
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Description</Label>
              <Input
                value={editDescription}
                onChange={(e) => {
                  setEditDescription(e.target.value)
                  setDirty(true)
                }}
                placeholder="Optional description"
                className="h-8 text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Content</Label>
              <Textarea
                value={editContent}
                onChange={(e) => {
                  setEditContent(e.target.value)
                  setDirty(true)
                }}
                rows={6}
                className="text-sm font-mono"
              />
            </div>

            {error && (
              <div className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
                {error}
              </div>
            )}
          </div>
        )}

        {!loading && prompt && (
          <DialogFooter className="gap-2 sm:gap-2">
            {onFill && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleFill}
                className="gap-1.5"
              >
                <FileDown className="h-3.5 w-3.5" />
                Fill
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!dirty || saving}
              className="gap-1.5"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
