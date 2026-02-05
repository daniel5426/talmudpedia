"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import { BaseNode } from "./BaseNode"
import { PipelineNodeData } from "../types"

function SourceNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  return (
    <BaseNode
      {...props}
      data={data}
    />
  )
}

export const SourceNode = memo(SourceNodeComponent)
