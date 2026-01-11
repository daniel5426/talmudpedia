"use client"

import { useMemo } from "react"
import { FolderInput, Scissors, Sparkles, Database } from "lucide-react"
import { cn } from "@/lib/utils"
import { 
  OperatorCategory, 
  OperatorSpec, 
  CATEGORY_COLORS, 
  CATEGORY_LABELS,
  DataType 
} from "./types"

interface OperatorCatalog {
  source: OperatorCatalogItem[]
  transform: OperatorCatalogItem[]
  embedding: OperatorCatalogItem[]
  storage: OperatorCatalogItem[]
}

interface OperatorCatalogItem {
  operator_id: string
  display_name: string
  input_type: DataType
  output_type: DataType
  dimension?: number
}

interface NodeCatalogProps {
  catalog: OperatorCatalog
  onDragStart: (event: React.DragEvent, operatorId: string, category: OperatorCategory) => void
}

const CATEGORY_ICONS: Record<OperatorCategory, React.ElementType> = {
  source: FolderInput,
  transform: Scissors,
  embedding: Sparkles,
  storage: Database,
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
  const Icon = CATEGORY_ICONS[category]
  const color = CATEGORY_COLORS[category]

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-md cursor-grab",
        "border border-transparent hover:border-border",
        "bg-muted/50 hover:bg-muted transition-colors"
      )}
      draggable
      onDragStart={onDragStart}
    >
      <div
        className="p-1 rounded"
        style={{ backgroundColor: `${color}20` }}
      >
        <Icon className="h-3.5 w-3.5" style={{ color }} />
      </div>
      <span className="text-sm font-medium truncate">{item.display_name}</span>
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
  const color = CATEGORY_COLORS[category]
  const label = CATEGORY_LABELS[category]

  if (items.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
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

export function NodeCatalog({ catalog, onDragStart }: NodeCatalogProps) {
  const categories: OperatorCategory[] = ["source", "transform", "embedding", "storage"]

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b">
        <h3 className="font-semibold text-sm">Operators</h3>
        <p className="text-xs text-muted-foreground mt-1">
          Drag operators onto the canvas
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {categories.map((category) => (
          <CategorySection
            key={category}
            category={category}
            items={catalog[category] || []}
            onDragStart={onDragStart}
          />
        ))}
      </div>
    </div>
  )
}
