"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import { Database } from "lucide-react"
import { BaseNode } from "./BaseNode"
import { PipelineNodeData, CATEGORY_COLORS } from "../types"

function StorageNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  return (
    <BaseNode
      {...props}
      data={data}
    />
  )
}

export const StorageNode = memo(StorageNodeComponent)
