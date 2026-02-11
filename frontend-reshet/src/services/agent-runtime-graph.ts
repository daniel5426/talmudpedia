import { Edge, Node } from "@xyflow/react"

import { AgentNodeData, AgentNodeType } from "@/components/agent-builder/types"
import type { AgentExecutionEvent, AgentRunTreeNode, AgentRunTreeResponse } from "@/services/agent"

type RuntimeExecutionStatus = "pending" | "running" | "completed" | "failed"

interface RuntimeGraphIndexes {
  eventSequenceByType: Record<string, number>
  childRunNodeByRunId: Record<string, string>
  groupNodeByGroupId: Record<string, string>
  spawnDecisionNodeBySourceNodeId: Record<string, string>
  joinDecisionNodeByGroupId: Record<string, string>
  authoritativeRunStatusByRunId: Record<string, string>
}

export interface RuntimeGraphState {
  runtimeNodes: Node<AgentNodeData>[]
  runtimeEdges: Edge[]
  takenStaticEdgeIds: string[]
  runtimeStatusByNodeId: Record<string, RuntimeExecutionStatus>
  runtimeNotesByNodeId: Record<string, string>
  indexes: RuntimeGraphIndexes
}

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled", "timed_out"])

const isTerminalRunStatus = (status?: string): boolean => {
  if (!status) return false
  return TERMINAL_RUN_STATUSES.has(status)
}

const toRuntimeExecutionStatus = (status?: string): RuntimeExecutionStatus => {
  if (!status) return "pending"
  if (status === "running" || status === "queued" || status === "paused" || status === "pending") return "running"
  if (status === "completed" || status === "completed_with_errors") return "completed"
  if (status === "failed" || status === "cancelled" || status === "timed_out" || status === "error" || status === "denied") return "failed"
  return "pending"
}

const emptyIndexes = (): RuntimeGraphIndexes => ({
  eventSequenceByType: {},
  childRunNodeByRunId: {},
  groupNodeByGroupId: {},
  spawnDecisionNodeBySourceNodeId: {},
  joinDecisionNodeByGroupId: {},
  authoritativeRunStatusByRunId: {},
})

export const createEmptyRuntimeGraphState = (): RuntimeGraphState => ({
  runtimeNodes: [],
  runtimeEdges: [],
  takenStaticEdgeIds: [],
  runtimeStatusByNodeId: {},
  runtimeNotesByNodeId: {},
  indexes: emptyIndexes(),
})

const nextEventSequence = (state: RuntimeGraphState, eventName: string): [RuntimeGraphState, number] => {
  const prev = state.indexes.eventSequenceByType[eventName] || 0
  const next = prev + 1
  return [{
    ...state,
    indexes: {
      ...state.indexes,
      eventSequenceByType: {
        ...state.indexes.eventSequenceByType,
        [eventName]: next,
      },
    },
  }, next]
}

const upsertRuntimeNode = (nodes: Node<AgentNodeData>[], node: Node<AgentNodeData>): Node<AgentNodeData>[] => {
  const idx = nodes.findIndex((item) => item.id === node.id)
  if (idx === -1) return [...nodes, node]
  const copy = [...nodes]
  copy[idx] = node
  return copy
}

const upsertRuntimeEdge = (edges: Edge[], edge: Edge): Edge[] => {
  const idx = edges.findIndex((item) => item.id === edge.id)
  if (idx === -1) return [...edges, edge]
  const copy = [...edges]
  copy[idx] = edge
  return copy
}

const getStaticNode = (staticNodes: Node<AgentNodeData>[], nodeId?: string | null): Node<AgentNodeData> | undefined => {
  if (!nodeId) return undefined
  return staticNodes.find((node) => node.id === nodeId)
}

const makeRuntimeNode = ({
  id,
  nodeType,
  displayName,
  config,
  executionStatus,
  position,
}: {
  id: string
  nodeType: AgentNodeType
  displayName: string
  config?: Record<string, unknown>
  executionStatus?: RuntimeExecutionStatus
  position: { x: number; y: number }
}): Node<AgentNodeData> => ({
  id,
  type: nodeType,
  position,
  draggable: true,
  connectable: false,
  selectable: true,
  deletable: false,
  data: {
    nodeType,
    category: "orchestration",
    displayName,
    config: config || {},
    inputType: "context",
    outputType: "context",
    isConfigured: true,
    hasErrors: false,
    executionStatus,
    runtime: true,
  } as AgentNodeData,
})

const updateRunNodeStatusIfAllowed = (
  state: RuntimeGraphState,
  runId: string,
  requestedStatus: string
): RuntimeGraphState => {
  const authoritative = state.indexes.authoritativeRunStatusByRunId[runId]
  if (authoritative && isTerminalRunStatus(authoritative) && requestedStatus !== authoritative) {
    return state
  }
  const nodeId = state.indexes.childRunNodeByRunId[runId]
  if (!nodeId) return state
  const targetNode = state.runtimeNodes.find((node) => node.id === nodeId)
  if (!targetNode) return state
  const patchedNode: Node<AgentNodeData> = {
    ...targetNode,
    data: {
      ...targetNode.data,
      executionStatus: toRuntimeExecutionStatus(requestedStatus),
      config: {
        ...(targetNode.data.config || {}),
        run_status: requestedStatus,
      },
    } as AgentNodeData,
  }
  return {
    ...state,
    runtimeNodes: upsertRuntimeNode(state.runtimeNodes, patchedNode),
  }
}

const ensureChildRunNode = (
  state: RuntimeGraphState,
  runId: string,
  position: { x: number; y: number },
  status = "queued"
): RuntimeGraphState => {
  const existingNodeId = state.indexes.childRunNodeByRunId[runId]
  if (existingNodeId) {
    return updateRunNodeStatusIfAllowed(state, runId, status)
  }

  const runtimeNodeId = `runtime-run:${runId}`
  const runNode = makeRuntimeNode({
    id: runtimeNodeId,
    nodeType: "agent",
    displayName: `Child Run ${runId.slice(0, 8)}`,
    executionStatus: toRuntimeExecutionStatus(status),
    config: { run_id: runId, run_status: status },
    position,
  })

  return {
    ...state,
    runtimeNodes: [...state.runtimeNodes, runNode],
    indexes: {
      ...state.indexes,
      childRunNodeByRunId: {
        ...state.indexes.childRunNodeByRunId,
        [runId]: runtimeNodeId,
      },
    },
  }
}

const ensureRuntimeGroupNode = (
  state: RuntimeGraphState,
  groupId: string,
  position: { x: number; y: number }
): RuntimeGraphState => {
  const existingNodeId = state.indexes.groupNodeByGroupId[groupId]
  if (existingNodeId) return state
  const runtimeNodeId = `runtime-group:${groupId}`
  const groupNode = makeRuntimeNode({
    id: runtimeNodeId,
    nodeType: "spawn_group",
    displayName: `Group ${groupId.slice(0, 8)}`,
    position,
    config: { group_id: groupId },
  })
  return {
    ...state,
    runtimeNodes: [...state.runtimeNodes, groupNode],
    indexes: {
      ...state.indexes,
      groupNodeByGroupId: {
        ...state.indexes.groupNodeByGroupId,
        [groupId]: runtimeNodeId,
      },
    },
  }
}

const markTakenStaticEdgeIds = (
  state: RuntimeGraphState,
  staticEdges: Edge[],
  sourceNodeId: string,
  sourceHandle: string
): RuntimeGraphState => {
  const taken = new Set(state.takenStaticEdgeIds)
  staticEdges.forEach((edge) => {
    const edgeSourceHandle = String((edge as any).sourceHandle || (edge as any).source_handle || "")
    if (edge.source === sourceNodeId && edgeSourceHandle === sourceHandle) {
      taken.add(edge.id)
    }
  })
  return {
    ...state,
    takenStaticEdgeIds: Array.from(taken),
  }
}

export const applyRuntimeEvent = (
  baseState: RuntimeGraphState,
  event: AgentExecutionEvent,
  staticNodes: Node<AgentNodeData>[],
  staticEdges: Edge[]
): RuntimeGraphState => {
  const eventName = typeof event.event === "string" ? event.event : ""
  if (!eventName) return baseState

  let state = baseState

  if (eventName === "orchestration.spawn_decision") {
    const runId = String(event.run_id || "")
    const sourceNodeId = String(event.span_id || "")
    if (!runId || !sourceNodeId) return state

    const sourceNode = getStaticNode(staticNodes, sourceNodeId)
    const sourcePosition = sourceNode?.position || { x: 0, y: 0 }
    const spawnedRunIds = Array.isArray(event.data?.spawned_run_ids)
      ? event.data?.spawned_run_ids.filter((item): item is string => typeof item === "string" && item.length > 0)
      : []

    let decisionNodeId = state.indexes.spawnDecisionNodeBySourceNodeId[sourceNodeId]
    if (!decisionNodeId) {
      const sequenceResult = nextEventSequence(state, eventName)
      state = sequenceResult[0]
      const seq = sequenceResult[1]
      decisionNodeId = `runtime-event:${runId}:${eventName}:${seq}`
      const decisionNode = makeRuntimeNode({
        id: decisionNodeId,
        nodeType: "spawn_run",
        displayName: "Spawn Decision",
        position: { x: sourcePosition.x + 240, y: sourcePosition.y + 80 },
        config: { source_node_id: sourceNodeId, ...event.data },
      })
      state = {
        ...state,
        runtimeNodes: upsertRuntimeNode(state.runtimeNodes, decisionNode),
        runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
          id: `runtime-edge:${sourceNodeId}:${decisionNodeId}`,
          source: sourceNodeId,
          target: decisionNodeId,
          animated: true,
          style: { stroke: "#1f2937", strokeWidth: 2, strokeDasharray: "6 3" },
        }),
        indexes: {
          ...state.indexes,
          spawnDecisionNodeBySourceNodeId: {
            ...state.indexes.spawnDecisionNodeBySourceNodeId,
            [sourceNodeId]: decisionNodeId,
          },
        },
      }
    } else {
      const currentNode = state.runtimeNodes.find((node) => node.id === decisionNodeId)
      if (currentNode) {
        const patchedNode: Node<AgentNodeData> = {
          ...currentNode,
          data: {
            ...currentNode.data,
            config: { ...(currentNode.data.config || {}), ...event.data },
          } as AgentNodeData,
        }
        state = { ...state, runtimeNodes: upsertRuntimeNode(state.runtimeNodes, patchedNode) }
      }
    }

    spawnedRunIds.forEach((childRunId, index) => {
      state = ensureChildRunNode(
        state,
        childRunId,
        { x: sourcePosition.x + 480, y: sourcePosition.y + index * 100 },
        "queued"
      )
      const childNodeId = state.indexes.childRunNodeByRunId[childRunId]
      if (childNodeId) {
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:${decisionNodeId}:${childNodeId}`,
            source: decisionNodeId,
            target: childNodeId,
            animated: true,
            style: { stroke: "#334155", strokeWidth: 2 },
          }),
        }
      }
    })
    return state
  }

  if (eventName === "orchestration.child_lifecycle") {
    const childRunId = String(event.data?.child_run_id || "")
    const lifecycleStatus = String(event.data?.status || "running")
    if (!childRunId) return state
    state = ensureChildRunNode(
      state,
      childRunId,
      { x: 560, y: 140 + state.runtimeNodes.length * 80 },
      lifecycleStatus
    )
    state = updateRunNodeStatusIfAllowed(state, childRunId, lifecycleStatus)

    const groupId = typeof event.data?.orchestration_group_id === "string"
      ? event.data.orchestration_group_id
      : ""
    if (groupId) {
      state = ensureRuntimeGroupNode(state, groupId, { x: 380, y: 120 + state.runtimeNodes.length * 24 })
      const groupNodeId = state.indexes.groupNodeByGroupId[groupId]
      const childNodeId = state.indexes.childRunNodeByRunId[childRunId]
      if (groupNodeId && childNodeId) {
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:${groupNodeId}:${childNodeId}`,
            source: groupNodeId,
            target: childNodeId,
            style: { stroke: "#64748b", strokeWidth: 1.8 },
          }),
        }
      }
    }
    return state
  }

  if (eventName === "orchestration.join_decision") {
    const runId = String(event.run_id || "")
    const sourceNodeId = String(event.span_id || "")
    const groupId = String(event.data?.group_id || "")
    if (!runId || !sourceNodeId) return state
    const sourcePosition = getStaticNode(staticNodes, sourceNodeId)?.position || { x: 0, y: 0 }
    let decisionNodeId = groupId ? state.indexes.joinDecisionNodeByGroupId[groupId] : undefined
    if (!decisionNodeId) {
      const sequenceResult = nextEventSequence(state, eventName)
      state = sequenceResult[0]
      const seq = sequenceResult[1]
      decisionNodeId = `runtime-event:${runId}:${eventName}:${seq}`
    }
    const decisionNode = makeRuntimeNode({
      id: decisionNodeId,
      nodeType: "join",
      displayName: "Join Decision",
      executionStatus: toRuntimeExecutionStatus(String(event.data?.status || "running")),
      position: { x: sourcePosition.x + 260, y: sourcePosition.y + 120 },
      config: { ...event.data, source_node_id: sourceNodeId },
    })
    state = {
      ...state,
      runtimeNodes: upsertRuntimeNode(state.runtimeNodes, decisionNode),
      runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
        id: `runtime-edge:${sourceNodeId}:${decisionNodeId}`,
        source: sourceNodeId,
        target: decisionNodeId,
        animated: true,
        style: { stroke: "#0f172a", strokeWidth: 2, strokeDasharray: "6 3" },
      }),
    }
    if (groupId) {
      state = {
        ...state,
        indexes: {
          ...state.indexes,
          joinDecisionNodeByGroupId: {
            ...state.indexes.joinDecisionNodeByGroupId,
            [groupId]: decisionNodeId,
          },
        },
      }
      const groupNodeId = state.indexes.groupNodeByGroupId[groupId]
      if (groupNodeId) {
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:${groupNodeId}:${decisionNodeId}`,
            source: groupNodeId,
            target: decisionNodeId,
            style: { stroke: "#64748b", strokeWidth: 1.8 },
          }),
        }
      }
    }
    return state
  }

  if (eventName === "orchestration.cancellation_propagation") {
    const cancelledRunIds = Array.isArray(event.data?.cancelled_run_ids)
      ? event.data.cancelled_run_ids.filter((item): item is string => typeof item === "string")
      : []
    const reason = String(event.data?.reason || "")
    cancelledRunIds.forEach((runId) => {
      state = updateRunNodeStatusIfAllowed(state, runId, "cancelled")
      const nodeId = state.indexes.childRunNodeByRunId[runId]
      if (!nodeId) return
      const targetNode = state.runtimeNodes.find((node) => node.id === nodeId)
      if (!targetNode) return
      const patchedNode: Node<AgentNodeData> = {
        ...targetNode,
        data: {
          ...targetNode.data,
          config: {
            ...(targetNode.data.config || {}),
            cancelled_reason: reason,
          },
        } as AgentNodeData,
      }
      state = {
        ...state,
        runtimeNodes: upsertRuntimeNode(state.runtimeNodes, patchedNode),
      }
    })
    return state
  }

  if (eventName === "orchestration.policy_deny") {
    const sourceNodeId = String(event.span_id || "")
    if (!sourceNodeId) return state
    return {
      ...state,
      runtimeStatusByNodeId: {
        ...state.runtimeStatusByNodeId,
        [sourceNodeId]: "failed",
      },
      runtimeNotesByNodeId: {
        ...state.runtimeNotesByNodeId,
        [sourceNodeId]: String(event.data?.reason || "Denied by policy"),
      },
    }
  }

  if (eventName === "node_end") {
    const sourceNodeId = String(event.span_id || "")
    const nextHandle = String((event.data?.output as Record<string, unknown> | undefined)?.next || "")
    if (!sourceNodeId || !nextHandle) return state
    return markTakenStaticEdgeIds(state, staticEdges, sourceNodeId, nextHandle)
  }

  if (process.env.NODE_ENV !== "production") {
    console.warn("[agent-runtime-graph] Ignored unknown event:", eventName, event)
  }
  return state
}

export const applyRuntimeEvents = (
  state: RuntimeGraphState,
  events: AgentExecutionEvent[],
  staticNodes: Node<AgentNodeData>[],
  staticEdges: Edge[]
): RuntimeGraphState => {
  return events.reduce(
    (acc, event) => applyRuntimeEvent(acc, event, staticNodes, staticEdges),
    state
  )
}

const walkRunTree = (root: AgentRunTreeNode): AgentRunTreeNode[] => {
  const out: AgentRunTreeNode[] = []
  const queue: AgentRunTreeNode[] = [root]
  while (queue.length > 0) {
    const next = queue.shift()
    if (!next) continue
    out.push(next)
    next.children.forEach((child) => queue.push(child))
  }
  return out
}

export const reconcileRuntimeTree = (
  baseState: RuntimeGraphState,
  treePayload: AgentRunTreeResponse
): RuntimeGraphState => {
  const allTreeNodes = walkRunTree(treePayload.tree)
  const rootRunId = String(treePayload.root_run_id || "")
  let state = baseState
  const nextAuthoritative: Record<string, string> = {
    ...state.indexes.authoritativeRunStatusByRunId,
  }

  allTreeNodes.forEach((treeNode, idx) => {
    const runId = treeNode.run_id
    nextAuthoritative[runId] = treeNode.status
    const isRootNode = runId === rootRunId && !treeNode.parent_run_id
    if (isRootNode) {
      return
    }
    const x = 540 + (treeNode.depth || 0) * 220
    const y = 80 + idx * 96
    state = ensureChildRunNode(state, runId, { x, y }, treeNode.status)
    state = updateRunNodeStatusIfAllowed(state, runId, treeNode.status)

    if (treeNode.parent_run_id) {
      const parentNodeId = state.indexes.childRunNodeByRunId[treeNode.parent_run_id]
      const childNodeId = state.indexes.childRunNodeByRunId[runId]
      if (parentNodeId && childNodeId) {
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:run:${parentNodeId}:${childNodeId}`,
            source: parentNodeId,
            target: childNodeId,
            style: { stroke: "#64748b", strokeWidth: 1.6 },
          }),
        }
      }
    }

    if (treeNode.parent_node_id) {
      const childNodeId = state.indexes.childRunNodeByRunId[runId]
      if (childNodeId) {
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:static:${treeNode.parent_node_id}:${childNodeId}`,
            source: treeNode.parent_node_id,
            target: childNodeId,
            animated: true,
            style: { stroke: "#334155", strokeWidth: 2, strokeDasharray: "5 4" },
          }),
        }
      }
    }

    treeNode.groups.forEach((group, groupIndex) => {
      const groupX = x - 150
      const groupY = y + groupIndex * 64
      state = ensureRuntimeGroupNode(state, group.group_id, { x: groupX, y: groupY })
      const groupNodeId = state.indexes.groupNodeByGroupId[group.group_id]
      if (!groupNodeId) return
      group.members.forEach((member) => {
        const childNodeId = state.indexes.childRunNodeByRunId[member.run_id]
        if (!childNodeId) return
        state = {
          ...state,
          runtimeEdges: upsertRuntimeEdge(state.runtimeEdges, {
            id: `runtime-edge:group:${groupNodeId}:${childNodeId}`,
            source: groupNodeId,
            target: childNodeId,
            style: { stroke: "#475569", strokeWidth: 1.4 },
          }),
        }
      })
    })
  })

  return {
    ...state,
    indexes: {
      ...state.indexes,
      authoritativeRunStatusByRunId: nextAuthoritative,
    },
  }
}
