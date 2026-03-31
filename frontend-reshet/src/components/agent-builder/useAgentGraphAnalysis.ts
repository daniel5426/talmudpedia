"use client"

import { startTransition, useEffect, useState } from "react"

import { agentService } from "@/services"
import type { AgentGraphAnalysis, AgentGraphDefinition } from "@/services/agent"
import { normalizeGraphDefinition } from "./graphspec"

export function useAgentGraphAnalysis(
  agentId: string | undefined,
  graphDefinition: AgentGraphDefinition,
) {
  const [analysis, setAnalysis] = useState<AgentGraphAnalysis | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!agentId) {
      setAnalysis(null)
      return
    }

    const normalizedGraphDefinition = normalizeGraphDefinition(graphDefinition)
    const handle = window.setTimeout(() => {
      setIsLoading(true)
      agentService
        .analyzeGraph(agentId, normalizedGraphDefinition)
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
  }, [agentId, graphDefinition])

  return { analysis, isLoading }
}
