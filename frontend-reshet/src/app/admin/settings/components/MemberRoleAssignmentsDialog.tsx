"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { SettingsMember, SettingsRole } from "@/services"

interface MemberRoleAssignmentsDialogProps {
  open: boolean
  member: SettingsMember | null
  roles: SettingsRole[]
  selectedRoleIds: string[]
  saving: boolean
  onSelectedRoleIdsChange: (next: string[]) => void
  onOpenChange: (open: boolean) => void
  onSave: () => void
}

export function MemberRoleAssignmentsDialog({
  open,
  member,
  roles,
  selectedRoleIds,
  saving,
  onSelectedRoleIdsChange,
  onOpenChange,
  onSave,
}: MemberRoleAssignmentsDialogProps) {
  const selectedSet = new Set(selectedRoleIds)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-base">Edit member roles</DialogTitle>
          <DialogDescription className="text-xs">
            Assign any number of existing roles to {member?.full_name || member?.email || "this member"}.
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
              const checked = selectedSet.has(role.id)
              return (
                <label
                  key={role.id}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/50 px-4 py-3 hover:bg-muted/20"
                >
                  <Checkbox
                    className="mt-0.5"
                    checked={checked}
                    onCheckedChange={(nextChecked) => {
                      if (nextChecked === true) {
                        onSelectedRoleIdsChange([...selectedRoleIds, role.id])
                        return
                      }
                      onSelectedRoleIdsChange(selectedRoleIds.filter((roleId) => roleId !== role.id))
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{role.name}</span>
                      {role.is_system ? <Badge variant="secondary" className="h-5 text-[10px]">System</Badge> : null}
                    </div>
                    {role.description ? (
                      <p className="mt-0.5 text-xs text-muted-foreground/75">{role.description}</p>
                    ) : null}
                  </div>
                </label>
              )
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving || !member}>
            {saving ? "Saving..." : "Save roles"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
