"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import {
  FolderInput,
  Scissors,
  Sparkles,
  Database,
  Hash,
  ShieldCheck,
  Sparkle,
  ArrowRightLeft,
  Search,
  SortAsc,
  Code
} from "lucide-react"
import { BaseNode as SharedBaseNode, SharedNodeData } from "../../builder/nodes/BaseNode"
import { PipelineNodeData, CATEGORY_COLORS, getHandleColor } from "../types"

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

function BaseNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  const color = CATEGORY_COLORS[data.category]
  const Icon = CATEGORY_ICONS[data.category] || Hash

  return (
    <SharedBaseNode
      {...props}
      data={data as unknown as SharedNodeData}
      icon={Icon}
      categoryColor={color}
      getHandleColor={getHandleColor as (type: string) => string}
    />
  )
}

export const BaseNode = memo(BaseNodeComponent)
