"use client"

import { Check } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { SettingsMember, SettingsRole } from "@/services"

interface MemberRoleAssignmentsDialogProps {
  open: boolean
  member: SettingsMember | null
  roles: SettingsRole[]
  selectedRoleId: string
  saving: boolean
  onSelectedRoleIdChange: (next: string) => void
  onOpenChange: (open: boolean) => void
  onSave: () => void
}

export function MemberRoleAssignmentsDialog({
  open,
  member,
  roles,
  selectedRoleId,
  saving,
  onSelectedRoleIdChange,
  onOpenChange,
  onSave,
}: MemberRoleAssignmentsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base">Edit organization role</DialogTitle>
          <DialogDescription className="text-xs">
            Assign exactly one organization role to {member?.full_name || member?.email || "this member"}.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {member ? (
            <div className="rounded-xl border border-border/60 bg-muted/20 px-4 py-3">
              <p className="text-sm font-medium text-foreground">{member.full_name || member.email}</p>
              <p className="text-xs text-muted-foreground/70">{member.email}</p>
            </div>
          ) : null}

          <div className="max-h-[48vh] space-y-2 overflow-y-auto">
            {roles.map((role) => {
              const selected = selectedRoleId === role.id
              return (
                <button
                  type="button"
                  key={role.id}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                    selected
                      ? "border-primary bg-primary/5"
                      : "border-border/50 hover:bg-muted/20"
                  )}
                  onClick={() => onSelectedRoleIdChange(role.id)}
                >
                  <div
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                      selected ? "border-primary bg-primary text-primary-foreground" : "border-border/60"
                    )}
                  >
                    {selected ? <Check className="h-3.5 w-3.5" /> : null}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{role.name}</span>
                      {role.is_preset ? <Badge variant="secondary" className="h-5 text-[10px]">Preset</Badge> : null}
                    </div>
                    {role.description ? (
                      <p className="mt-0.5 text-xs text-muted-foreground/75">{role.description}</p>
                    ) : null}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving || !member || !selectedRoleId}>
            {saving ? "Saving..." : "Save role"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
