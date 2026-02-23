"use client"

import { useEffect, useState } from "react"
import { useDirection } from "@/components/direction-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Loader2, Pencil, Plus } from "lucide-react"
import {
  modelsService,
  LogicalModel,
  ModelProviderType,
  CreateProviderRequest,
  UpdateProviderRequest,
  ModelProviderSummary,
  IntegrationCredential,
  LLM_PROVIDER_OPTIONS,
} from "@/services"

export const PROVIDER_LABELS: Record<ModelProviderType, string> = Object.fromEntries(
  LLM_PROVIDER_OPTIONS.map((option) => [option.key, option.label])
) as Record<ModelProviderType, string>

export function AddProviderDialog({
  model,
  credentials,
  onAdded,
}: {
  model: LogicalModel
  credentials: IntegrationCredential[]
  onAdded: () => void
}) {
  const { direction } = useDirection()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState<CreateProviderRequest>({
    provider: "openai",
    provider_model_id: "",
    priority: 0,
    credentials_ref: undefined,
  })
  const providerCredentials = credentials.filter(
    (cred) => cred.category === "llm_provider" && cred.provider_key === form.provider
  )

  useEffect(() => {
    setForm((prev) => {
      if (prev.credentials_ref && !providerCredentials.find((cred) => cred.id === prev.credentials_ref)) {
        return { ...prev, credentials_ref: undefined }
      }
      return prev
    })
  }, [form.provider, credentials, providerCredentials])

  const handleAdd = async () => {
    if (!form.provider_model_id) return
    setLoading(true)
    try {
      const payload = {
        ...form,
        credentials_ref: form.credentials_ref || undefined,
      }
      await modelsService.addProvider(model.id, payload)
      setOpen(false)
      setForm({ provider: "openai", provider_model_id: "", priority: 0 })
      onAdded()
    } catch (error) {
      console.error("Failed to add provider", error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="h-3 w-3 mr-1" />
          Add Provider
        </Button>
      </DialogTrigger>
      <DialogContent dir={direction}>
        <DialogHeader>
          <DialogTitle>Add Provider to {model.name}</DialogTitle>
          <DialogDescription>Configure a provider binding for runtime resolution.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Select value={form.provider} onValueChange={(v) => setForm({ ...form, provider: v as ModelProviderType })}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LLM_PROVIDER_OPTIONS.map((option) => (
                  <SelectItem key={option.key} value={option.key}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Provider Model ID</Label>
            <Input
              placeholder="gpt-4o-2024-08-06"
              value={form.provider_model_id}
              onChange={(e) => setForm({ ...form, provider_model_id: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Credentials</Label>
            <Select
              value={form.credentials_ref || "platform_default"}
              onValueChange={(v) => setForm({ ...form, credentials_ref: v === "platform_default" ? undefined : v })}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select credentials" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="platform_default">Platform Default (ENV)</SelectItem>
                {providerCredentials.map((cred) => (
                  <SelectItem key={cred.id} value={cred.id}>
                    {cred.display_name}
                    {cred.is_default ? " (Default)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="add-provider-priority">Priority (lower = higher priority)</Label>
            <Input
              id="add-provider-priority"
              type="number"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value, 10) || 0 })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={!form.provider_model_id || loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Add Provider
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function EditProviderDialog({
  model,
  provider,
  credentials,
  onUpdated,
}: {
  model: LogicalModel
  provider: ModelProviderSummary
  credentials: IntegrationCredential[]
  onUpdated: () => void
}) {
  const { direction } = useDirection()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState<UpdateProviderRequest>({
    provider_model_id: provider.provider_model_id,
    priority: provider.priority,
    is_enabled: provider.is_enabled,
    credentials_ref: provider.credentials_ref ?? undefined,
  })
  const providerCredentials = credentials.filter(
    (cred) => cred.category === "llm_provider" && cred.provider_key === provider.provider
  )

  useEffect(() => {
    if (!open) return
    setForm({
      provider_model_id: provider.provider_model_id,
      priority: provider.priority,
      is_enabled: provider.is_enabled,
      credentials_ref: provider.credentials_ref ?? undefined,
    })
  }, [open, provider])

  const handleSave = async () => {
    setLoading(true)
    try {
      await modelsService.updateProvider(model.id, provider.id, form)
      setOpen(false)
      onUpdated()
    } catch (error) {
      console.error("Failed to update provider", error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" data-testid={`edit-provider-${provider.id}`}>
          <Pencil className="h-3 w-3" />
        </Button>
      </DialogTrigger>
      <DialogContent dir={direction}>
        <DialogHeader>
          <DialogTitle>Edit Provider Binding</DialogTitle>
          <DialogDescription>Update provider routing and credentials.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Input value={PROVIDER_LABELS[provider.provider] || provider.provider} disabled />
          </div>
          <div className="space-y-2">
            <Label>Provider Model ID</Label>
            <Input value={form.provider_model_id || ""} onChange={(e) => setForm({ ...form, provider_model_id: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Credentials</Label>
            <Select
              value={form.credentials_ref || "platform_default"}
              onValueChange={(v) => setForm({ ...form, credentials_ref: v === "platform_default" ? undefined : v })}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select credentials" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="platform_default">Platform Default (ENV)</SelectItem>
                {providerCredentials.map((cred) => (
                  <SelectItem key={cred.id} value={cred.id}>
                    {cred.display_name}
                    {cred.is_default ? " (Default)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-provider-priority">Priority (lower = higher priority)</Label>
            <Input
              id="edit-provider-priority"
              type="number"
              value={form.priority ?? 0}
              onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value, 10) || 0 })}
            />
          </div>
          <div className="flex items-center gap-3">
            <Checkbox checked={!!form.is_enabled} onCheckedChange={(v) => setForm({ ...form, is_enabled: v === true })} />
            <Label>Enabled</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
