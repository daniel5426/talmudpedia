"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import { Scissors } from "lucide-react"
import { BaseNode } from "./BaseNode"
import { PipelineNodeData, CATEGORY_COLORS } from "../types"

function TransformNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  return (
    <BaseNode
      {...props}
      data={data}
      icon={
        <Scissors
          className="h-4 w-4"
          style={{ color: CATEGORY_COLORS.transform }}
        />
      }
    />
  )
}

export const TransformNode = memo(TransformNodeComponent)
