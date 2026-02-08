"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { useDirection } from "@/components/direction-provider"
import { credentialsService, IntegrationCredential, IntegrationCredentialCategory } from "@/services"
import { cn } from "@/lib/utils"
import { Loader2, Plus, RefreshCw, Trash2, Pencil } from "lucide-react"

const CATEGORY_LABELS: Record<IntegrationCredentialCategory, { title: string; description: string }> = {
  llm_provider: {
    title: "LLM Providers",
    description: "API keys and base URLs for chat, embedding, and reranker models.",
  },
  vector_store: {
    title: "Vector Stores",
    description: "Credentials for Pinecone, Qdrant, and other vector backends.",
  },
  artifact_secret: {
    title: "Artifact Secrets",
    description: "Secrets used by custom artifacts and external integrations.",
  },
  custom: {
    title: "Custom Credentials",
    description: "Tenant-specific credentials for bespoke integrations.",
  },
}

function CredentialFormDialog({
  mode,
  category,
  credential,
  onSaved,
}: {
  mode: "create" | "edit"
  category: IntegrationCredentialCategory
  credential?: IntegrationCredential
  onSaved: () => void
}) {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [providerKey, setProviderKey] = useState(credential?.provider_key || "")
  const [providerVariant, setProviderVariant] = useState(credential?.provider_variant || "")
  const [displayName, setDisplayName] = useState(credential?.display_name || "")
  const [credentialsText, setCredentialsText] = useState("{}")
  const [isEnabled, setIsEnabled] = useState(credential?.is_enabled ?? true)

  useEffect(() => {
    if (open) {
      setProviderKey(credential?.provider_key || "")
      setProviderVariant(credential?.provider_variant || "")
      setDisplayName(credential?.display_name || "")
      setCredentialsText("{}")
      setIsEnabled(credential?.is_enabled ?? true)
      setError(null)
    }
  }, [open, credential])

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    let parsedCredentials: Record<string, unknown> = {}
    try {
      parsedCredentials = credentialsText.trim() ? JSON.parse(credentialsText) : {}
    } catch {
      setError("Credentials must be valid JSON.")
      setLoading(false)
      return
    }

    try {
      if (mode === "create") {
        await credentialsService.createCredential({
          category,
          provider_key: providerKey,
          provider_variant: providerVariant || null,
          display_name: displayName,
          credentials: parsedCredentials,
          is_enabled: isEnabled,
        })
      } else if (credential) {
        await credentialsService.updateCredential(credential.id, {
          category,
          provider_key: providerKey,
          provider_variant: providerVariant || null,
          display_name: displayName,
          credentials: parsedCredentials,
          is_enabled: isEnabled,
        })
      }
      setOpen(false)
      onSaved()
    } catch (err) {
      console.error("Failed to save credential", err)
      setError("Failed to save credential.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {mode === "create" ? (
          <Button size="sm">
            <Plus className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
            Add Credential
          </Button>
        ) : (
          <Button variant="ghost" size="icon">
            <Pencil className="h-4 w-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent dir={direction}>
        <DialogHeader>
          <DialogTitle className={isRTL ? "text-right" : "text-left"}>
            {mode === "create" ? "Add Credential" : "Edit Credential"}
          </DialogTitle>
          <DialogDescription className={isRTL ? "text-right" : "text-left"}>
            Credentials are stored securely and never shown after saving.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Provider Key</Label>
            <Input value={providerKey} onChange={(e) => setProviderKey(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Provider Variant (optional)</Label>
            <Input value={providerVariant} onChange={(e) => setProviderVariant(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Display Name</Label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Credentials (JSON)</Label>
            <Textarea
              value={credentialsText}
              onChange={(e) => setCredentialsText(e.target.value)}
              className="font-mono text-xs"
              rows={6}
            />
          </div>
          <div className="flex items-center gap-3">
            <Checkbox checked={isEnabled} onCheckedChange={(v) => setIsEnabled(v === true)} />
            <Label>Enabled</Label>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={loading || !providerKey || !displayName}>
            {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function SettingsPage() {
  const { direction } = useDirection()
  const isRTL = direction === "rtl"
  const [credentials, setCredentials] = useState<IntegrationCredential[]>([])
  const [loading, setLoading] = useState(true)

  const fetchCredentials = useCallback(async () => {
    setLoading(true)
    try {
      const data = await credentialsService.listCredentials()
      setCredentials(data)
    } catch (error) {
      console.error("Failed to fetch credentials", error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCredentials()
  }, [fetchCredentials])

  const grouped = useMemo(() => {
    return credentials.reduce<Record<IntegrationCredentialCategory, IntegrationCredential[]>>((acc, cred) => {
      acc[cred.category] = acc[cred.category] || []
      acc[cred.category].push(cred)
      return acc
    }, {
      llm_provider: [],
      vector_store: [],
      artifact_secret: [],
      custom: [],
    })
  }, [credentials])

  const handleDelete = async (credential: IntegrationCredential) => {
    if (!confirm("Delete this credential? This cannot be undone.")) return
    try {
      await credentialsService.deleteCredential(credential.id)
      fetchCredentials()
    } catch (error) {
      console.error("Failed to delete credential", error)
    }
  }

  return (
    <div className="flex flex-col h-full w-full" dir={direction}>
      <header className="h-12 flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <CustomBreadcrumb items={[{ label: "Settings", href: "/admin/settings", active: true }]} />
        <Button variant="outline" size="sm" className="h-9" onClick={fetchCredentials}>
          <RefreshCw className={cn("h-4 w-4", isRTL ? "ml-2" : "mr-2")} />
          Refresh
        </Button>
      </header>

      <div className="flex-1 overflow-auto p-4 space-y-6">
        {loading ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              Loading settings...
            </CardContent>
          </Card>
        ) : (
          (Object.keys(CATEGORY_LABELS) as IntegrationCredentialCategory[]).map((category) => {
            const categoryInfo = CATEGORY_LABELS[category]
            const items = grouped[category] || []
            return (
              <Card key={category}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-lg">{categoryInfo.title}</CardTitle>
                      <CardDescription>{categoryInfo.description}</CardDescription>
                    </div>
                    <CredentialFormDialog
                      mode="create"
                      category={category}
                      onSaved={fetchCredentials}
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  {items.length === 0 ? (
                    <div className="text-sm text-muted-foreground">No credentials configured.</div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Display Name</TableHead>
                          <TableHead>Provider</TableHead>
                          <TableHead>Variant</TableHead>
                          <TableHead>Keys</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="w-[70px]"></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {items.map((cred) => (
                          <TableRow key={cred.id}>
                            <TableCell>{cred.display_name}</TableCell>
                            <TableCell className="font-mono text-xs">{cred.provider_key}</TableCell>
                            <TableCell className="font-mono text-xs">{cred.provider_variant || "-"}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {cred.credential_keys.length ? cred.credential_keys.join(", ") : "None"}
                            </TableCell>
                            <TableCell>
                              <Badge variant={cred.is_enabled ? "default" : "outline"}>
                                {cred.is_enabled ? "Enabled" : "Disabled"}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1">
                                <CredentialFormDialog
                                  mode="edit"
                                  category={category}
                                  credential={cred}
                                  onSaved={fetchCredentials}
                                />
                                <Button variant="ghost" size="icon" onClick={() => handleDelete(cred)}>
                                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            )
          })
        )}
      </div>
    </div>
  )
}
