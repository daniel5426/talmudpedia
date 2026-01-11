"use client"

import { memo } from "react"
import { NodeProps } from "@xyflow/react"
import { FolderInput } from "lucide-react"
import { BaseNode } from "./BaseNode"
import { PipelineNodeData, CATEGORY_COLORS } from "../types"

function SourceNodeComponent(props: NodeProps) {
  const data = props.data as PipelineNodeData
  return (
    <BaseNode
      {...props}
      data={data}
      icon={
        <FolderInput
          className="h-4 w-4"
          style={{ color: CATEGORY_COLORS.source }}
        />
      }
    />
  )
}

export const SourceNode = memo(SourceNodeComponent)
