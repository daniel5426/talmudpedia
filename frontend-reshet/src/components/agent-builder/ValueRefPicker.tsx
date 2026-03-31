"use client"

import { useMemo } from "react"

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { AgentGraphAnalysis } from "@/services/agent"
import {
  getValueRefGroups,
  isValueRefSemanticTypeCompatible,
  isValueRefTypeCompatible,
  type ValueRef,
} from "./graph-contract"

function encodeValueRef(valueRef?: ValueRef) {
  if (!valueRef) return ""
  return JSON.stringify({
    namespace: valueRef.namespace,
    node_id: valueRef.node_id || undefined,
    key: valueRef.key,
  })
}

function decodeValueRef(raw: string): ValueRef | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as ValueRef
  } catch {
    return null
  }
}

export function ValueRefPicker({
  analysis,
  nodeId,
  value,
  onChange,
  expectedTypes,
  expectedSemanticTypes,
  triggerClassName,
}: {
  analysis?: AgentGraphAnalysis | null
  nodeId?: string | null
  value?: ValueRef | null
  onChange: (value: ValueRef | null) => void
  expectedTypes?: string[]
  expectedSemanticTypes?: string[]
  triggerClassName?: string
}) {
  const groups = useMemo(() => getValueRefGroups(analysis, nodeId), [analysis, nodeId])
  const selected = encodeValueRef(value || undefined)
  const optionsByEncodedValue = useMemo(() => {
    const entries = groups.flatMap((group) =>
      group.options.map((option) => [encodeValueRef(option.value_ref), option] as const),
    )
    return new Map(entries)
  }, [groups])

  const filteredGroups = useMemo(
    () =>
      groups
        .map((group) => ({
          ...group,
          options: group.options.filter(
            (option) =>
              isValueRefTypeCompatible(option.type, expectedTypes)
              && isValueRefSemanticTypeCompatible(option.semantic_type, expectedSemanticTypes),
          ),
        }))
        .filter((group) => group.options.length > 0),
    [expectedSemanticTypes, expectedTypes, groups],
  )

  return (
    <Select
      value={selected}
      onValueChange={(next) => {
        onChange(optionsByEncodedValue.get(next)?.value_ref || decodeValueRef(next))
      }}
    >
      <SelectTrigger
        aria-label="Select value"
        className={triggerClassName || "h-9 w-[220px] max-w-full min-w-0 rounded-lg border-none bg-muted/40 text-[13px] shadow-none focus:ring-1 focus:ring-offset-0 [&>span]:truncate"}
      >
        <SelectValue placeholder="Select value..." />
      </SelectTrigger>
      <SelectContent className="rounded-xl border-border/50" data-value-ref-picker-portal="true">
        {filteredGroups.map((group) => (
          <SelectGroup key={group.label}>
            <SelectLabel>{group.label}</SelectLabel>
            {group.options.map((option) => {
              const encoded = encodeValueRef(option.value_ref)
              return (
                <SelectItem key={`${group.label}:${option.node_id || "global"}:${option.key}`} value={encoded}>
                  {(option.label || option.key) + (option.type ? ` (${option.type})` : "")}
                </SelectItem>
              )
            })}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  )
}
