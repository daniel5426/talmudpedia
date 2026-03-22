"use client"

import { startTransition, useEffect, useState } from "react"
import { Edge, Node } from "@xyflow/react"

import { agentService } from "@/services"
import type { AgentGraphAnalysis } from "@/services/agent"
import { AgentNodeData } from "./types"
import { normalizeGraphSpecForSave } from "./graphspec"

export function useAgentGraphAnalysis(
  agentId: string | undefined,
  nodes: Node<AgentNodeData>[],
  edges: Edge[],
) {
  const [analysis, setAnalysis] = useState<AgentGraphAnalysis | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!agentId) {
      setAnalysis(null)
      return
    }

    const graphDefinition = normalizeGraphSpecForSave(nodes, edges, { specVersion: "3.0" })
    const handle = window.setTimeout(() => {
      setIsLoading(true)
      agentService
        .analyzeGraph(agentId, graphDefinition)
        .then((response) => {
          startTransition(() => {
            setAnalysis(response.analysis)
          })
        })
        .catch((error) => {
          console.error("Failed to analyze agent graph:", error)
        })
        .finally(() => setIsLoading(false))
    }, 180)

    return () => window.clearTimeout(handle)
  }, [agentId, edges, nodes])

  return { analysis, isLoading }
}
