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
  PricingConfig,
  IntegrationCredential,
  LLM_PROVIDER_OPTIONS,
  getModelProviderOptions,
  isTenantManagedPricingProvider,
} from "@/services"

export const PROVIDER_LABELS: Record<ModelProviderType, string> = Object.fromEntries(
  LLM_PROVIDER_OPTIONS.map((option) => [option.key, option.label])
) as Record<ModelProviderType, string>

const BILLING_MODE_OPTIONS = [
  { value: "unknown", label: "Unknown" },
  { value: "per_1k_tokens", label: "Per 1K Tokens" },
  { value: "per_token", label: "Per Token" },
  { value: "flat_per_request", label: "Flat Per Request" },
] as const

function normalizePricingConfig(pricingConfig?: PricingConfig): PricingConfig {
  const config = pricingConfig || {}
  return {
    currency: String(config.currency || "USD"),
    billing_mode: config.billing_mode || "unknown",
    rates: {
      input: Number(config.rates?.input || 0),
      output: Number(config.rates?.output || 0),
    },
    minimum_charge: config.minimum_charge ?? undefined,
    flat_amount: config.flat_amount ?? undefined,
  }
}

function buildPricingPayload(pricingConfig: PricingConfig): PricingConfig {
  const billingMode = pricingConfig.billing_mode || "unknown"
  const payload: PricingConfig = {
    currency: String(pricingConfig.currency || "USD").trim().toUpperCase() || "USD",
    billing_mode: billingMode,
  }
  if (
    pricingConfig.minimum_charge !== undefined &&
    pricingConfig.minimum_charge !== null &&
    !Number.isNaN(Number(pricingConfig.minimum_charge))
  ) {
    payload.minimum_charge = Number(pricingConfig.minimum_charge)
  }
  if (billingMode === "per_1k_tokens" || billingMode === "per_token") {
    payload.rates = {}
    if (pricingConfig.rates?.input !== undefined) payload.rates.input = Number(pricingConfig.rates.input)
    if (pricingConfig.rates?.output !== undefined) payload.rates.output = Number(pricingConfig.rates.output)
  }
  if (billingMode === "flat_per_request" && pricingConfig.flat_amount !== undefined) {
    payload.flat_amount = Number(pricingConfig.flat_amount)
  }
  return payload
}

function PricingFields({
  pricingConfig,
  onChange,
}: {
  pricingConfig: PricingConfig
  onChange: (next: PricingConfig) => void
}) {
  const billingMode = pricingConfig.billing_mode || "unknown"
  return (
    <div className="space-y-4 rounded-md border p-3">
      <div className="space-y-2">
        <Label htmlFor="provider-billing-mode">Billing Mode</Label>
        <Select value={billingMode} onValueChange={(value) => onChange({ ...pricingConfig, billing_mode: value as PricingConfig["billing_mode"] })}>
          <SelectTrigger id="provider-billing-mode" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BILLING_MODE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="provider-pricing-currency">Currency</Label>
        <Input
          id="provider-pricing-currency"
          value={pricingConfig.currency || "USD"}
          onChange={(e) => onChange({ ...pricingConfig, currency: e.target.value })}
          placeholder="USD"
        />
      </div>
      {(billingMode === "per_1k_tokens" || billingMode === "per_token") && (
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="provider-pricing-input-rate">Input Rate</Label>
            <Input
              id="provider-pricing-input-rate"
              type="number"
              step="0.000001"
              value={pricingConfig.rates?.input ?? ""}
              onChange={(e) =>
                onChange({
                  ...pricingConfig,
                  rates: { ...(pricingConfig.rates || {}), input: e.target.value === "" ? 0 : Number(e.target.value) },
                })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-pricing-output-rate">Output Rate</Label>
            <Input
              id="provider-pricing-output-rate"
              type="number"
              step="0.000001"
              value={pricingConfig.rates?.output ?? ""}
              onChange={(e) =>
                onChange({
                  ...pricingConfig,
                  rates: { ...(pricingConfig.rates || {}), output: e.target.value === "" ? 0 : Number(e.target.value) },
                })
              }
            />
          </div>
        </div>
      )}
      {billingMode === "flat_per_request" && (
        <div className="space-y-2">
          <Label htmlFor="provider-pricing-flat-amount">Flat Amount</Label>
          <Input
            id="provider-pricing-flat-amount"
            type="number"
            step="0.000001"
            value={pricingConfig.flat_amount ?? ""}
            onChange={(e) => onChange({ ...pricingConfig, flat_amount: e.target.value === "" ? undefined : Number(e.target.value) })}
          />
        </div>
      )}
      <div className="space-y-2">
        <Label htmlFor="provider-pricing-minimum-charge">Minimum Charge</Label>
        <Input
          id="provider-pricing-minimum-charge"
          type="number"
          step="0.000001"
          value={pricingConfig.minimum_charge ?? ""}
          onChange={(e) => onChange({ ...pricingConfig, minimum_charge: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
      </div>
    </div>
  )
}

function PlatformManagedPricingNotice() {
  return (
    <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
      Platform-managed pricing. Organization pricing is only editable for custom and local providers.
    </div>
  )
}

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
    provider: getModelProviderOptions(model.capability_type)[0]?.key || "openai",
    provider_model_id: "",
    priority: 0,
    credentials_ref: undefined,
    pricing_config: normalizePricingConfig(),
  })
  const providerOptions = getModelProviderOptions(model.capability_type)
  const canEditPricing = isTenantManagedPricingProvider(form.provider)
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
        ...(canEditPricing
          ? { pricing_config: buildPricingPayload(form.pricing_config || {}) }
          : {}),
      }
      await modelsService.addProvider(model.id, payload)
      setOpen(false)
      setForm({
        provider: providerOptions[0]?.key || "openai",
        provider_model_id: "",
        priority: 0,
        pricing_config: normalizePricingConfig(),
      })
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
                {providerOptions.map((option) => (
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
          {canEditPricing ? (
            <PricingFields
              pricingConfig={normalizePricingConfig(form.pricing_config)}
              onChange={(pricing_config) => setForm({ ...form, pricing_config })}
            />
          ) : (
            <PlatformManagedPricingNotice />
          )}
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
    pricing_config: normalizePricingConfig(provider.pricing_config),
  })
  const canEditPricing = isTenantManagedPricingProvider(provider.provider)
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
      pricing_config: normalizePricingConfig(provider.pricing_config),
    })
  }, [open, provider])

  const handleSave = async () => {
    setLoading(true)
    try {
      await modelsService.updateProvider(model.id, provider.id, {
        ...form,
        ...(canEditPricing
          ? { pricing_config: buildPricingPayload(form.pricing_config || {}) }
          : {}),
      })
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
          {canEditPricing ? (
            <PricingFields
              pricingConfig={normalizePricingConfig(form.pricing_config)}
              onChange={(pricing_config) => setForm({ ...form, pricing_config })}
            />
          ) : (
            <PlatformManagedPricingNotice />
          )}
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
