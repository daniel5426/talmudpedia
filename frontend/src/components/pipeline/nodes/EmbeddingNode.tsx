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
      icon={
        <Sparkles
          className="h-4 w-4"
          style={{ color: CATEGORY_COLORS.embedding }}
        />
      }
    />
  )
}

export const EmbeddingNode = memo(EmbeddingNodeComponent)
