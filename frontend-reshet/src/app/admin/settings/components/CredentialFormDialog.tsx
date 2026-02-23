"use client"

import { useEffect, useMemo, useState } from "react"
import { useDirection } from "@/components/direction-provider"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Loader2, Pencil, Plus } from "lucide-react"
import {
  credentialsService,
  IntegrationCredential,
  IntegrationCredentialCategory,
  LLM_PROVIDER_OPTIONS,
  TOOL_PROVIDER_OPTIONS,
  VECTOR_STORE_PROVIDER_OPTIONS,
} from "@/services"

interface CredentialFormDialogProps {
  mode: "create" | "edit"
  category: IntegrationCredentialCategory
  credential?: IntegrationCredential
  disabled?: boolean
  onSaved: () => void
}

function getCategoryProviderOptions(category: IntegrationCredentialCategory): Array<{ key: string; label: string }> | null {
  if (category === "llm_provider") return LLM_PROVIDER_OPTIONS
  if (category === "vector_store") return VECTOR_STORE_PROVIDER_OPTIONS
  if (category === "tool_provider") return TOOL_PROVIDER_OPTIONS
  return null
}

export function CredentialFormDialog({
  mode,
  category,
  credential,
  disabled,
  onSaved,
}: CredentialFormDialogProps) {
  const { direction } = useDirection()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [providerKey, setProviderKey] = useState(credential?.provider_key || "")
  const [apiKey, setApiKey] = useState("")
  const [isEnabled, setIsEnabled] = useState(credential?.is_enabled ?? true)
  const [isDefault, setIsDefault] = useState(credential?.is_default ?? true)

  const providerOptions = useMemo(() => getCategoryProviderOptions(category), [category])

  useEffect(() => {
    if (!open) return
    const firstProvider = providerOptions?.[0]?.key || ""
    setProviderKey(credential?.provider_key || firstProvider)
    setApiKey("")
    setIsEnabled(credential?.is_enabled ?? true)
    setIsDefault(credential?.is_default ?? true)
    setError(null)
  }, [open, credential, providerOptions])

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    const key = apiKey.trim()
    if (!key) {
      setError("API key is required.")
      setLoading(false)
      return
    }

    const normalizedProviderKey = providerKey.trim().toLowerCase()
    const displayNameFromCatalog = providerOptions?.find((option) => option.key === normalizedProviderKey)?.label
    const effectiveDisplayName = credential?.display_name || displayNameFromCatalog || normalizedProviderKey || "credential"

    try {
      if (mode === "create") {
        await credentialsService.createCredential({
          category,
          provider_key: normalizedProviderKey,
          provider_variant: null,
          display_name: effectiveDisplayName,
          credentials: { api_key: key },
          is_enabled: isEnabled,
          is_default: isDefault,
        })
      } else if (credential) {
        await credentialsService.updateCredential(credential.id, {
          category,
          provider_key: normalizedProviderKey,
          provider_variant: null,
          display_name: effectiveDisplayName,
          credentials: { api_key: key },
          is_enabled: isEnabled,
          is_default: isDefault,
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
          <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" disabled={disabled}>
            <Plus className="h-3 w-3" />
            Add
          </Button>
        ) : (
          <Button variant="ghost" size="icon" className="h-7 w-7" disabled={disabled}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent dir={direction} className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Add Credential" : "Edit Credential"}</DialogTitle>
          <DialogDescription>Credentials are stored securely and never shown after saving.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label className="text-xs font-medium text-muted-foreground">Provider</Label>
            {providerOptions ? (
              <Select value={providerKey || providerOptions[0]?.key} onValueChange={setProviderKey}>
                <SelectTrigger className="h-9 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providerOptions.map((provider) => (
                    <SelectItem key={provider.key} value={provider.key}>
                      {provider.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={providerKey} onChange={(e) => setProviderKey(e.target.value)} className="h-9" />
            )}
          </div>
          <div className="space-y-2">
            <Label className="text-xs font-medium text-muted-foreground">API Key</Label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={mode === "edit" ? "Enter new key to rotate" : "Enter API key"}
              className="h-9 font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground/70">Stored values are write-only and are not shown after save.</p>
          </div>
          <label className="flex items-center gap-3 cursor-pointer">
            <Checkbox checked={isEnabled} onCheckedChange={(v) => setIsEnabled(v === true)} />
            <span className="text-sm">Enabled</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <Checkbox checked={isDefault} onCheckedChange={(v) => setIsDefault(v === true)} />
            <span className="text-sm">Set as default</span>
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading || !providerKey || !apiKey.trim()}>
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

