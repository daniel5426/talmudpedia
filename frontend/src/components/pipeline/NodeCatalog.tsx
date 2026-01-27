"use client"

import { useMemo, useState } from "react"
import {
  Search,
  GripVertical,
  FolderInput,
  Scissors,
  Sparkles,
  Database,
  Hash,
  ShieldCheck,
  Sparkle,
  ArrowRightLeft,
  SortAsc,
  Code,
  Plus,
  PanelLeftClose
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  OperatorCategory,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  DataType
} from "./types"

interface OperatorCatalogItem {
  operator_id: string
  display_name: string
  input_type: DataType
  output_type: DataType
  dimension?: number
}

type OperatorCatalog = Partial<Record<OperatorCategory, OperatorCatalogItem[]>>

interface NodeCatalogProps {
  catalog: OperatorCatalog
  onDragStart: (event: React.DragEvent, operatorId: string, category: OperatorCategory) => void
  onAddCustomOperator?: () => void
  onClose?: () => void
}

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  source: FolderInput,
  normalization: ShieldCheck,
  enrichment: Sparkle,
  chunking: Scissors,
  transform: ArrowRightLeft,
  embedding: Sparkles,
  storage: Database,
  retrieval: Search,
  reranking: SortAsc,
  custom: Code,
}

function CatalogItem({
  item,
  category,
  onDragStart
}: {
  item: OperatorCatalogItem
  category: OperatorCategory
  onDragStart: (event: React.DragEvent) => void
}) {
  const Icon = CATEGORY_ICONS[category] || Hash
  const color = CATEGORY_COLORS[category]

  return (
    <div
      className={cn(
        "group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-grab active:cursor-grabbing",
        "border border-transparent bg-muted/30 hover:bg-background hover:border-border",
        "transition-all duration-200"
      )}
      draggable
      onDragStart={onDragStart}
    >
      <div
        className="shrink-0 p-1.5 rounded-md transition-transform group-hover:scale-105"
        style={{ backgroundColor: color }}
      >
        <Icon className="h-3.5 w-3.5 text-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-[13px] font-medium text-foreground/80 truncate block">
          {item.display_name}
        </span>
      </div>
      <GripVertical className="h-3.5 w-3.5 text-muted-foreground/10 group-hover:text-muted-foreground/30 transition-colors" />
    </div>
  )
}

function CategorySection({
  category,
  items,
  onDragStart
}: {
  category: OperatorCategory
  items: OperatorCatalogItem[]
  onDragStart: (event: React.DragEvent, operatorId: string, category: OperatorCategory) => void
}) {
  const label = CATEGORY_LABELS[category]

  if (!items || items.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-[9px] font-bold uppercase tracking-[0.1em] text-muted-foreground/50">
          {label}
        </span>
      </div>
      <div className="space-y-1">
        {items.map((item) => (
          <CatalogItem
            key={item.operator_id}
            item={item}
            category={category}
            onDragStart={(e) => onDragStart(e, item.operator_id, category)}
          />
        ))}
      </div>
    </div>
  )
}

export function NodeCatalog({ catalog, onDragStart, onAddCustomOperator, onClose }: NodeCatalogProps) {
  const [search, setSearch] = useState("")

  const categories: OperatorCategory[] = [
    "source",
    "normalization",
    "enrichment",
    "chunking",
    "embedding",
    "storage",
    "retrieval",
    "reranking",
    "custom",
    "transform"
  ]

  return (
    <div className="h-full flex flex-col">
      <div className="p-3.5 space-y-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {onClose && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-md -ml-1 text-muted-foreground hover:text-foreground"
                onClick={onClose}
                title="Close Catalog"
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            )}
            <h3 className="text-xs font-bold text-foreground/70 uppercase tracking-tight">Operators</h3>
          </div>
          {onAddCustomOperator && (
            <Button variant="ghost" size="icon" className="h-6 w-6 rounded-md" onClick={onAddCustomOperator}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input
            placeholder="Search..."
            className="pl-8 h-8 bg-muted/40 border-none rounded-lg text-[11px] focus-visible:ring-1 focus-visible:ring-offset-0"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3.5 pb-6 space-y-6 scrollbar-none">
        {categories.map((category) => (
          <CategorySection
            key={category}
            category={category}
            items={(catalog[category] || []).filter(item =>
              item.display_name.toLowerCase().includes(search.toLowerCase())
            )}
            onDragStart={onDragStart}
          />
        ))}
        {categories.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <p className="text-[11px] text-muted-foreground">No matches</p>
          </div>
        )}
      </div>
    </div>
  )
}
