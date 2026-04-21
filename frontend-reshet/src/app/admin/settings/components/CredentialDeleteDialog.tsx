"use client"

import { useEffect, useMemo, useState } from "react"
import { useDirection } from "@/components/direction-provider"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Loader2, Trash2 } from "lucide-react"
import { CredentialUsageResponse, IntegrationCredential, credentialsService } from "@/services"

interface CredentialDeleteDialogProps {
  credential: IntegrationCredential
  disabled?: boolean
  onDeleted: () => void
  onError: (message: string) => void
}

export function CredentialDeleteDialog({ credential, disabled, onDeleted, onError }: CredentialDeleteDialogProps) {
  const { direction } = useDirection()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [usage, setUsage] = useState<CredentialUsageResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const totalLinks = useMemo(() => {
    if (!usage) return 0
    return usage.model_providers.length + usage.knowledge_stores.length + usage.tools.length
  }, [usage])

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    credentialsService
      .getCredentialUsage(credential.id)
      .then((data) => {
        if (!active) return
        setUsage(data)
      })
      .catch((err) => {
        console.error("Failed to load credential usage", err)
        if (!active) return
        setError("Failed to load connected resources.")
      })
      .finally(() => {
        if (!active) return
        setLoading(false)
      })

    return () => {
      active = false
    }
  }, [open, credential.id])

  const handleDelete = async () => {
    setDeleting(true)
    setError(null)
    onError("")
    try {
      await credentialsService.deleteCredential(credential.id, { force_disconnect: totalLinks > 0 })
      setOpen(false)
      onDeleted()
    } catch (err: any) {
      console.error("Failed to delete credential", err)
      const detail = err?.response?.data?.detail
      const message = typeof detail === "string" ? detail : "Failed to delete credential."
      setError(message)
      onError(message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground/50 hover:text-destructive" disabled={disabled}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent dir={direction} className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>Delete Credential</DialogTitle>
          <DialogDescription>
            {totalLinks > 0
              ? "This credential is connected to resources. Deleting it will disconnect them and they will use Platform Default (ENV)."
              : "This credential is not connected. It will be permanently removed."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 max-h-[360px] overflow-auto py-1">
          {loading && (
            <div className="text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading connected resources...
            </div>
          )}

          {!loading && usage && (
            <>
              <p className="text-xs text-muted-foreground">
                Connected resources: <span className="font-medium text-foreground">{totalLinks}</span>
              </p>

              {usage.model_providers.length > 0 && (
                <div className="rounded-md border border-border/50 p-3">
                  <p className="text-xs font-medium mb-2">Model Providers</p>
                  <div className="space-y-1.5">
                    {usage.model_providers.map((row) => (
                      <p key={row.binding_id} className="text-xs text-muted-foreground">
                        {row.model_name} · {row.provider} · {row.provider_model_id}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {usage.knowledge_stores.length > 0 && (
                <div className="rounded-md border border-border/50 p-3">
                  <p className="text-xs font-medium mb-2">Knowledge Stores</p>
                  <div className="space-y-1.5">
                    {usage.knowledge_stores.map((row) => (
                      <p key={row.store_id} className="text-xs text-muted-foreground">
                        {row.store_name} · {row.backend}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {usage.tools.length > 0 && (
                <div className="rounded-md border border-border/50 p-3">
                  <p className="text-xs font-medium mb-2">Tools</p>
                  <div className="space-y-1.5">
                    {usage.tools.map((row) => (
                      <p key={row.tool_id} className="text-xs text-muted-foreground">
                        {row.tool_name}{row.builtin_key ? ` (${row.builtin_key})` : ""}{row.implementation_type ? ` · ${row.implementation_type}` : ""}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {!loading && error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleDelete} disabled={deleting || loading}>
            {deleting && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
            {totalLinks > 0 ? "Delete and Disconnect" : "Delete Credential"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
