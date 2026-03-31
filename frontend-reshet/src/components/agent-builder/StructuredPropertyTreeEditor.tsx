"use client"

import { Braces, FileText, Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { AgentGraphAnalysis } from "@/services/agent"
import { createStructuredProperty, type StructuredPropertyDefinition } from "./graph-contract"
import { ValueRefPicker } from "./ValueRefPicker"

const PROPERTY_TYPES = [
  { value: "string", label: "STR" },
  { value: "number", label: "NUM" },
  { value: "boolean", label: "BOOL" },
  { value: "object", label: "OBJ" },
  { value: "list", label: "LIST" },
] as const

function updateNodeAtPath(
  nodes: StructuredPropertyDefinition[],
  path: number[],
  updater: (node: StructuredPropertyDefinition) => StructuredPropertyDefinition,
): StructuredPropertyDefinition[] {
  if (path.length === 0) return nodes
  const [head, ...rest] = path
  return nodes.map((node, index) => {
    if (index !== head) return node
    if (rest.length === 0) return updater(node)
    return {
      ...node,
      children: updateNodeAtPath(node.children || [], rest, updater),
    }
  })
}

function removeNodeAtPath(nodes: StructuredPropertyDefinition[], path: number[]): StructuredPropertyDefinition[] {
  if (path.length === 0) return nodes
  const [head, ...rest] = path
  if (rest.length === 0) return nodes.filter((_, index) => index !== head)
  return nodes.map((node, index) => {
    if (index !== head) return node
    return {
      ...node,
      children: removeNodeAtPath(node.children || [], rest),
    }
  })
}

function appendChildAtPath(
  nodes: StructuredPropertyDefinition[],
  path: number[],
  child: StructuredPropertyDefinition,
): StructuredPropertyDefinition[] {
  if (path.length === 0) return [...nodes, child]
  const [head, ...rest] = path
  return nodes.map((node, index) => {
    if (index !== head) return node
    if (rest.length === 0) {
      return {
        ...node,
        children: [...(node.children || []), child],
      }
    }
    return {
      ...node,
      children: appendChildAtPath(node.children || [], rest, child),
    }
  })
}

function PropertyRows({
  properties,
  depth,
  mode,
  nodeId,
  analysis,
  onChange,
}: {
  properties: StructuredPropertyDefinition[]
  depth: number
  mode: "description" | "value"
  nodeId?: string | null
  analysis?: AgentGraphAnalysis | null
  onChange: (properties: StructuredPropertyDefinition[]) => void
}) {
  return (
    <div className="space-y-1">
      {properties.map((property, index) => {
        const path = [index]
        const icon = property.type === "object"
          ? <Braces className="h-4 w-4 text-violet-500" />
          : <FileText className="h-4 w-4 text-emerald-500" />
        return (
          <div key={property.id} className="space-y-1">
            <div
              className="grid grid-cols-[24px_minmax(0,1fr)_118px_minmax(0,1fr)_32px] gap-0 rounded-xl px-2 "
              style={{ paddingLeft: `${depth * 28}px` }}
            >
              <div className="flex items-center justify-center pr-2">{icon}</div>
              <Input
                value={property.key}
                onChange={(event) =>
                  onChange(updateNodeAtPath(properties, path, (current) => ({ ...current, key: event.target.value })))
                }
                placeholder="property name"
                className="h-9 min-h-9 rounded-r-none rounded-l-lg border-r-0 border-border/50 bg-background/80 text-[13px] shadow-none"
              />
              <Select
                value={property.type}
                onValueChange={(nextType) =>
                  onChange(
                    updateNodeAtPath(properties, path, (current) => ({
                      ...current,
                      type: nextType as StructuredPropertyDefinition["type"],
                      children: nextType === "object" ? current.children || [] : [],
                    })),
                  )
                }
              >
                <SelectTrigger className="h-9 min-h-9 w-full min-w-0 rounded-none border-r-0 border-border/50 bg-background/80 px-2.5 py-0 text-[13px] shadow-none [&>span]:flex [&>span]:h-full [&>span]:items-center">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROPERTY_TYPES.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {mode === "description" ? (
                <Input
                  value={property.description || ""}
                  onChange={(event) =>
                    onChange(
                      updateNodeAtPath(properties, path, (current) => ({
                        ...current,
                        description: event.target.value,
                      })),
                    )
                  }
                  placeholder="Add description"
                  className="h-9 min-h-9 rounded-none border-r-0 border-l border-border/50 bg-background/80 text-[13px] shadow-none"
                />
              ) : (
                <div className="min-w-0">
                  <ValueRefPicker
                    analysis={analysis}
                    nodeId={nodeId}
                    value={property.value_ref || undefined}
                    expectedTypes={[property.type === "list" ? "list" : property.type]}
                    triggerClassName="h-9 min-h-9 w-full max-w-full min-w-0 rounded-none border-r-0 border-l border-border/50 bg-background/80 text-[13px] shadow-none focus:ring-0 [&>span]:truncate"
                    onChange={(valueRef) =>
                      onChange(
                        updateNodeAtPath(properties, path, (current) => ({
                          ...current,
                          value_ref: valueRef,
                        })),
                      )
                    }
                  />
                </div>
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-l-none rounded-r-lg border border-l-0 border-border/50 bg-background/80 text-muted-foreground/60 hover:bg-background"
                onClick={() => onChange(removeNodeAtPath(properties, path))}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            {property.type === "object" ? (
              <div className="space-y-3">
                <PropertyRows
                  properties={property.children || []}
                  depth={depth + 1}
                  mode={mode}
                  nodeId={nodeId}
                  analysis={analysis}
                  onChange={(children) =>
                    onChange(updateNodeAtPath(properties, path, (current) => ({ ...current, children })))
                  }
                />
                <div style={{ paddingLeft: `${(depth + 1) * 28 + 28}px` }}>
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-8 mb-2.5 rounded-lg border border-border/40 bg-background/70 px-3 text-[12px] text-foreground/75 hover:bg-background"
                    onClick={() =>
                      onChange(appendChildAtPath(properties, path, createStructuredProperty()))
                    }
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    Add property
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

export function StructuredPropertyTreeEditor({
  properties,
  mode,
  nodeId,
  analysis,
  onChange,
}: {
  properties: StructuredPropertyDefinition[]
  mode: "description" | "value"
  nodeId?: string | null
  analysis?: AgentGraphAnalysis | null
  onChange: (properties: StructuredPropertyDefinition[]) => void
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[28px_minmax(0,1fr)_124px_minmax(0,1fr)_36px] gap-3 px-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/55">
        <div />
        <div>Name</div>
        <div>Type</div>
        <div>{mode === "description" ? "Description" : "Value"}</div>
        <div />
      </div>
      <PropertyRows
        properties={properties}
        depth={0}
        mode={mode}
        nodeId={nodeId}
        analysis={analysis}
        onChange={onChange}
      />
      <Button
        type="button"
        variant="ghost"
        className="h-8 rounded-lg border border-dashed border-border/50 bg-muted/20 px-3 text-[12px] text-foreground/75 hover:bg-muted/35"
        onClick={() => onChange([...properties, createStructuredProperty()])}
      >
        <Plus className="mr-1 h-4 w-4" />
        Add property
      </Button>
    </div>
  )
}
