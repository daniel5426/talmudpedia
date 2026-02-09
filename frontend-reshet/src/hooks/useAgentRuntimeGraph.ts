"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { applyNodeChanges, Edge, Node, NodeChange } from "@xyflow/react"

import { AgentNodeData } from "@/components/agent-builder/types"
import { agentService } from "@/services"
import type { AgentExecutionEvent, AgentRunStatus } from "@/services"
import {
  applyRuntimeEvents,
  createEmptyRuntimeGraphState,
  reconcileRuntimeTree,
  RuntimeGraphState,
} from "@/services/agent-runtime-graph"

interface UseAgentRuntimeGraphParams {
  staticNodes: Node<AgentNodeData>[]
  staticEdges: Edge[]
  runId: string | null
  executionEvents: AgentExecutionEvent[]
  runStatus: AgentRunStatus["status"] | null
}

interface UseAgentRuntimeGraphResult {
  runtimeNodes: Node<AgentNodeData>[]
  runtimeEdges: Edge[]
  takenStaticEdgeIds: string[]
  runtimeStatusByNodeId: Record<string, "pending" | "running" | "completed" | "failed">
  runtimeNotesByNodeId: Record<string, string>
  isReconciling: boolean
  reconcileError: string | null
  applyRuntimeNodeChanges: (changes: NodeChange<Node<AgentNodeData>>[]) => void
  setRuntimeNodes: (nodes: Node<AgentNodeData>[]) => void
  clearRuntimeOverlay: () => void
}

const TERMINAL_STATUSES = new Set<AgentRunStatus["status"]>(["completed", "failed", "cancelled"])

export function useAgentRuntimeGraph({
  staticNodes,
  staticEdges,
  runId,
  executionEvents,
  runStatus,
}: UseAgentRuntimeGraphParams): UseAgentRuntimeGraphResult {
  const [state, setState] = useState<RuntimeGraphState>(() => createEmptyRuntimeGraphState())
  const [isReconciling, setIsReconciling] = useState(false)
  const [reconcileError, setReconcileError] = useState<string | null>(null)
  const processedEventsRef = useRef(0)
  const reconciledTerminalRunRef = useRef<string | null>(null)

  const clearRuntimeOverlay = useCallback(() => {
    setState(createEmptyRuntimeGraphState())
    setReconcileError(null)
    processedEventsRef.current = executionEvents.length
    reconciledTerminalRunRef.current = null
  }, [executionEvents.length])

  const applyRuntimeNodeChanges = useCallback((changes: NodeChange<Node<AgentNodeData>>[]) => {
    if (!changes.length) return
    setState((prev) => ({
      ...prev,
      runtimeNodes: applyNodeChanges(changes, prev.runtimeNodes).map((node) => ({
        ...node,
        draggable: true,
        selectable: true,
        connectable: false,
      })),
    }))
  }, [])

  const setRuntimeNodes = useCallback((nodes: Node<AgentNodeData>[]) => {
    setState((prev) => ({
      ...prev,
      runtimeNodes: nodes.map((node) => ({
        ...node,
        draggable: true,
        selectable: true,
        connectable: false,
      })),
    }))
  }, [])

  useEffect(() => {
    setState(createEmptyRuntimeGraphState())
    setReconcileError(null)
    processedEventsRef.current = 0
    reconciledTerminalRunRef.current = null
  }, [runId])

  useEffect(() => {
    if (!runId) return
    if (executionEvents.length <= processedEventsRef.current) return
    const nextEvents = executionEvents.slice(processedEventsRef.current)
    processedEventsRef.current = executionEvents.length
    setState((prev) => applyRuntimeEvents(prev, nextEvents, staticNodes, staticEdges))
  }, [executionEvents, runId, staticNodes, staticEdges])

  const runTreeReconcile = useCallback(async () => {
    if (!runId) return
    setIsReconciling(true)
    try {
      const tree = await agentService.getRunTree(runId)
      setState((prev) => reconcileRuntimeTree(prev, tree))
      setReconcileError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to reconcile run tree"
      setReconcileError(message)
    } finally {
      setIsReconciling(false)
    }
  }, [runId])

  useEffect(() => {
    if (!runId) return
    if (runStatus !== "running" && runStatus !== "paused") return
    void runTreeReconcile()
    const interval = window.setInterval(() => {
      void runTreeReconcile()
    }, 2000)
    return () => window.clearInterval(interval)
  }, [runId, runStatus, runTreeReconcile])

  useEffect(() => {
    if (!runId || !runStatus || !TERMINAL_STATUSES.has(runStatus)) return
    if (reconciledTerminalRunRef.current === runId) return
    reconciledTerminalRunRef.current = runId
    void runTreeReconcile()
  }, [runId, runStatus, runTreeReconcile])

  return useMemo(() => ({
    runtimeNodes: state.runtimeNodes,
    runtimeEdges: state.runtimeEdges,
    takenStaticEdgeIds: state.takenStaticEdgeIds,
    runtimeStatusByNodeId: state.runtimeStatusByNodeId,
    runtimeNotesByNodeId: state.runtimeNotesByNodeId,
    isReconciling,
    reconcileError,
    applyRuntimeNodeChanges,
    setRuntimeNodes,
    clearRuntimeOverlay,
  }), [state, isReconciling, reconcileError, applyRuntimeNodeChanges, setRuntimeNodes, clearRuntimeOverlay])
}
