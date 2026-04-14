"use client"

import { useCallback, useEffect, useState } from "react"
import { modelsService, toolsService } from "@/services"
import type { ToolDefinition } from "@/services/agent"

type ReadyCache = {
  status: "ready"
  modelLabels: Map<string, string>
  tools: ToolDefinition[]
}

type CacheState =
  | { status: "idle" }
  | { status: "loading" }
  | ReadyCache
  | { status: "error"; error: unknown }

let sharedPromise: Promise<ReadyCache> | null = null
let sharedReady: ReadyCache | null = null

function loadCanvasResources(): Promise<ReadyCache> {
  if (sharedReady) return Promise.resolve(sharedReady)
  if (!sharedPromise) {
    sharedPromise = (async () => {
      const [modelsRes, toolsRes] = await Promise.all([
        modelsService.listModels("chat", "active", 0, 100, "full"),
        toolsService.listTools(undefined, "published", undefined, 0, 100, "summary"),
      ])
      const modelLabels = new Map<string, string>()
      for (const m of modelsRes.items || []) {
        modelLabels.set(m.id, m.name)
      }
      const tools = toolsRes.items || []
      const next: ReadyCache = { status: "ready", modelLabels, tools }
      sharedReady = next
      return next
    })()
  }
  return sharedPromise
}

export function useAgentBuilderCanvasResources() {
  const [state, setState] = useState<CacheState>(() => sharedReady ?? { status: "idle" })

  useEffect(() => {
    if (sharedReady) {
      setState(sharedReady)
      return
    }
    let cancelled = false
    setState({ status: "loading" })
    loadCanvasResources()
      .then((ready) => {
        if (!cancelled) setState(ready)
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", error })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const getModelLabel = useCallback(
    (id: string | undefined) => {
      if (!id || state.status !== "ready") return null
      return state.modelLabels.get(id) ?? null
    },
    [state]
  )

  const getToolById = useCallback(
    (id: string) => {
      if (state.status !== "ready") return undefined
      return state.tools.find((t) => t.id === id)
    },
    [state]
  )

  return {
    loading: state.status === "loading" || state.status === "idle",
    error: state.status === "error" ? state.error : null,
    ready: state.status === "ready",
    getModelLabel,
    getToolById,
  }
}
