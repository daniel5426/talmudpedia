"use client"

import { useState, useCallback } from "react"
import { Node, Edge } from "@xyflow/react"

interface HistoryState<TNodeData extends Record<string, unknown> = Record<string, unknown>> {
  nodes: Node<TNodeData>[]
  edges: Edge[]
}

interface UseBuilderHistoryOptions<TNodeData extends Record<string, unknown> = Record<string, unknown>> {
  initialNodes: Node<TNodeData>[]
  initialEdges: Edge[]
}

interface UseBuilderHistoryReturn<TNodeData extends Record<string, unknown> = Record<string, unknown>> {
  history: HistoryState<TNodeData>[]
  historyIndex: number
  canUndo: boolean
  canRedo: boolean
  takeSnapshot: (nodes: Node<TNodeData>[], edges: Edge[]) => void
  undo: () => HistoryState<TNodeData> | null
  redo: () => HistoryState<TNodeData> | null
}

/**
 * Shared hook for undo/redo functionality in builder UIs.
 * Manages history state and provides methods to navigate through it.
 */
export function useBuilderHistory<TNodeData extends Record<string, unknown> = Record<string, unknown>>({
  initialNodes,
  initialEdges,
}: UseBuilderHistoryOptions<TNodeData>): UseBuilderHistoryReturn<TNodeData> {
  const [history, setHistory] = useState<HistoryState<TNodeData>[]>([
    { nodes: initialNodes, edges: initialEdges }
  ])
  const [historyIndex, setHistoryIndex] = useState(0)

  const takeSnapshot = useCallback((nodes: Node<TNodeData>[], edges: Edge[]) => {
    const nextState = { nodes: [...nodes], edges: [...edges] }
    
    setHistory(prev => {
      const nextHistory = prev.slice(0, historyIndex + 1)
      // Only add if different from last state
      const last = nextHistory[nextHistory.length - 1]
      if (last && JSON.stringify(last) === JSON.stringify(nextState)) {
        return nextHistory
      }
      return [...nextHistory, nextState]
    })
    setHistoryIndex(prev => prev + 1)
  }, [historyIndex])

  const undo = useCallback((): HistoryState<TNodeData> | null => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1
      setHistoryIndex(newIndex)
      return history[newIndex]
    }
    return null
  }, [history, historyIndex])

  const redo = useCallback((): HistoryState<TNodeData> | null => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1
      setHistoryIndex(newIndex)
      return history[newIndex]
    }
    return null
  }, [history, historyIndex])

  return {
    history,
    historyIndex,
    canUndo: historyIndex > 0,
    canRedo: historyIndex < history.length - 1,
    takeSnapshot,
    undo,
    redo,
  }
}
