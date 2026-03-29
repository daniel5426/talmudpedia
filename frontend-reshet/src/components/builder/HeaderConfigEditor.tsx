"use client"

import { ReactNode, useEffect, useRef, useState } from "react"
import { Check, Copy, FileText, PencilLine, X } from "lucide-react"
import { motion } from "motion/react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

interface HeaderConfigEditorProps {
  name: string
  description: string
  onNameChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  nameLabel?: string
  descriptionLabel?: string
  namePlaceholder?: string
  descriptionPlaceholder?: string
  triggerLabel?: string
  identifier?: string
  identifierLabel?: string
  disabled?: boolean
  defaultOpen?: boolean
  className?: string
  contentClassName?: string
  children?: ReactNode
}

export function HeaderConfigEditor({
  name,
  description,
  onNameChange,
  onDescriptionChange,
  nameLabel = "Name",
  descriptionLabel = "Description",
  namePlaceholder = "Enter a name",
  descriptionPlaceholder = "Add a short description",
  triggerLabel = "Edit details",
  identifier,
  identifierLabel = "ID",
  disabled = false,
  defaultOpen = false,
  className,
  contentClassName,
  children,
}: HeaderConfigEditorProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [isCopied, setIsCopied] = useState(false)
  const copyResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fieldIdBase = triggerLabel.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "") || "config"
  const collapsedWidth = 40
  const expandedWidth = "min(420px, calc(100vw - 2rem))"

  useEffect(() => {
    setOpen(defaultOpen)
  }, [defaultOpen])

  useEffect(() => {
    return () => {
      if (copyResetTimeoutRef.current) {
        clearTimeout(copyResetTimeoutRef.current)
      }
    }
  }, [])

  const handleCopyIdentifier = async () => {
    if (!identifier || typeof window === "undefined" || !navigator?.clipboard?.writeText) {
      return
    }
    await navigator.clipboard.writeText(identifier)
    setIsCopied(true)
    if (copyResetTimeoutRef.current) {
      clearTimeout(copyResetTimeoutRef.current)
    }
    copyResetTimeoutRef.current = setTimeout(() => {
      setIsCopied(false)
    }, 2000)
  }

  return (
    <div className={cn("relative h-8 w-[122px] shrink-0", className)}>
      <motion.div
        initial={false}
        animate={{
          width: open ? expandedWidth : collapsedWidth,
          height: open ? "auto" : 32,
          boxShadow: open ? "0 1px 7px rgba(0, 0, 0, 0.15)" : "none",
          borderRadius: open ? 8 : 8,
        }}
        transition={{
          type: "spring",
          stiffness: 340,
          damping: 28,
          mass: 0.9,
        }}
        style={{ transformOrigin: "top right" }}
        className={cn(
          "absolute right-0 top-0 z-[90] overflow-hidden bg-background/95 backdrop-blur-sm",
          "shadow-none",
          contentClassName
        )}
      >
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          disabled={disabled}
          className={cn(
            "absolute left-0 top-0 z-10 flex h-8 items-center px-3 text-xs transition-colors outline-none",
            "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            open ? "pointer-events-none opacity-0" : "w-full justify-start gap-2 text-foreground hover:bg-muted/60",
            disabled && "cursor-not-allowed opacity-50"
          )}
          aria-hidden={open}
          tabIndex={open ? -1 : 0}
        >
          <PencilLine className="h-3.5 w-3.5" />
        </button>
        <motion.div
          initial={false}
          animate={{
            opacity: open ? 1 : 0,
            y: open ? 0 : -8,
          }}
          transition={{
            duration: open ? 0.2 : 0.12,
            ease: "easeOut",
          }}
          className={cn(
            "pointer-events-none h-full px-3 pb-3 pt-2",
            open && "pointer-events-auto"
          )}
        >
          <div className="mb-4 flex items-center justify-between gap-3 text-xs font-medium uppercase tracking-[0.22em] text-muted-foreground/70">
            <div className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5" />
              Config
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={disabled}
              className="flex h-8 w-8 items-center justify-center rounded-md text-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`${fieldIdBase}-name`} className="text-xs font-medium text-foreground/80">
                {nameLabel}
              </Label>
              <Input
                id={`${fieldIdBase}-name`}
                value={name}
                onChange={(event) => onNameChange(event.target.value)}
                placeholder={namePlaceholder}
                className="h-10 border-border/60 bg-muted/20"
                disabled={disabled}
              />
            </div>
            {identifier && (
              <div className="space-y-2">
                <Label className="text-xs font-medium text-foreground/80">
                  {identifierLabel}
                </Label>
                <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-3 py-2">
                  <code className="min-w-0 flex-1 truncate text-xs text-foreground/85">
                    {identifier}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 shrink-0 gap-1.5 px-2 text-[11px]"
                    onClick={handleCopyIdentifier}
                    disabled={disabled}
                    aria-label="Copy agent ID"
                  >
                    {isCopied ? (
                      <>
                        <Check className="h-3.5 w-3.5" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor={`${fieldIdBase}-description`} className="text-xs font-medium text-foreground/80">
                {descriptionLabel}
              </Label>
              <Textarea
                id={`${fieldIdBase}-description`}
                value={description}
                onChange={(event) => onDescriptionChange(event.target.value)}
                placeholder={descriptionPlaceholder}
                className="min-h-24 resize-none border-border/60 bg-muted/20"
                disabled={disabled}
              />
            </div>
            {children}
          </div>
        </motion.div>
      </motion.div>
    </div>
  )
}
