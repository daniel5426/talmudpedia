import { Edge, Node } from "@xyflow/react"

import { AgentNodeData } from "./types"

export interface ExecuteRenderOverlay {
  runtimeNodes: Node<AgentNodeData>[]
  runtimeEdges: Edge[]
  runtimeStatusByNodeId: Record<string, "pending" | "running" | "completed" | "failed">
  runtimeNotesByNodeId: Record<string, string>
  takenStaticEdgeIds: string[]
}

export function mergeExecuteRenderGraph(
  staticNodes: Node<AgentNodeData>[],
  staticEdges: Edge[],
  overlay: ExecuteRenderOverlay
): { nodes: Node<AgentNodeData>[]; edges: Edge[] } {
  const staticWithRuntime = staticNodes.map((node) => {
    const runtimeStatus = overlay.runtimeStatusByNodeId[node.id]
    const runtimeNote = overlay.runtimeNotesByNodeId[node.id]
    return {
      ...node,
      draggable: false,
      data: {
        ...(node.data as AgentNodeData),
        executionStatus: runtimeStatus || (node.data as AgentNodeData).executionStatus,
        hasErrors: Boolean((node.data as AgentNodeData).hasErrors || runtimeNote),
      } as AgentNodeData,
    }
  })

  const taken = new Set(overlay.takenStaticEdgeIds)
  const highlightedStaticEdges = staticEdges.map((edge) => {
    if (!taken.has(edge.id)) {
      return edge
    }
    return {
      ...edge,
      animated: true,
      style: {
        ...(edge.style || {}),
        stroke: "#16a34a",
        strokeWidth: 3,
      },
    }
  })

  return {
    nodes: [...staticWithRuntime, ...overlay.runtimeNodes],
    edges: [...highlightedStaticEdges, ...overlay.runtimeEdges],
  }
}

export function getRenderGraphForMode(
  mode: "build" | "execute",
  staticNodes: Node<AgentNodeData>[],
  staticEdges: Edge[],
  overlay: ExecuteRenderOverlay
): { nodes: Node<AgentNodeData>[]; edges: Edge[] } {
  if (mode !== "execute") {
    return { nodes: staticNodes, edges: staticEdges }
  }
  return mergeExecuteRenderGraph(staticNodes, staticEdges, overlay)
}
