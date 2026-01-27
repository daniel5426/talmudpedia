"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import { Sparkles } from "lucide-react"
import { BaseNode } from "./BaseNode"
import { PipelineNodeData, CATEGORY_COLORS } from "../types"

function EmbeddingNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  return (
    <BaseNode
      {...props}
      data={data}
    />
  )
}

export const EmbeddingNode = memo(EmbeddingNodeComponent)
