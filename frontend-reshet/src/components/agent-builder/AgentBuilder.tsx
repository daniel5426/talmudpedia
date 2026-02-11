"use client"

import { useCallback, useState, useRef, useEffect, useMemo } from "react"
import {
    ReactFlow,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    addEdge,
    Connection,
    Edge,
    Node,
    NodeChange,
    ReactFlowProvider,
    useReactFlow,
    BackgroundVariant,
    SelectionMode,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { nanoid } from "nanoid"

import { nodeTypes } from "./nodes"
import { NodeCatalog } from "./NodeCatalog"
import { ConfigPanel } from "./ConfigPanel"
import { ExecutionPanel } from "./ExecutionPanel"
import { NodeTracePanel } from "./NodeTracePanel"
import { useAgentRunController, ExecutionStep } from "@/hooks/useAgentRunController"
import { useAgentRuntimeGraph } from "@/hooks/useAgentRuntimeGraph"
import {
    FloatingPanel,
    BuilderToolbar,
    ToolbarButton,
    CatalogToggleButton,
    useBuilderHistory,
    InteractionMode,
} from "@/components/builder"
import {
    AgentNodeSpec,
    AgentNodeData,
    AgentNodeCategory,
    AgentNodeType,
    canConnect,
    getNodeSpec,
} from "./types"
import { normalizeBuilderNode, normalizeBuilderEdges } from "./graphspec"
import { getRenderGraphForMode } from "./runtime-merge"
import { AgentExecutionEvent } from "@/services"
import { AlertTriangle, LayoutGrid, Trash2 } from "lucide-react"

interface AgentBuilderProps {
    agentId?: string
    initialNodes?: Node<AgentNodeData>[]
    initialEdges?: Edge[]
    onSave?: (nodes: Node<AgentNodeData>[], edges: Edge[]) => void
    onCompile?: () => void
    onRun?: () => void
    isSaving?: boolean
    isCompiling?: boolean
}

function matchesStepToNode(step: ExecutionStep, node: Node<AgentNodeData>, data: AgentNodeData): boolean {
    return (
        step.name === data.displayName ||
        step.name.toLowerCase() === data.nodeType.toLowerCase() ||
        step.id.includes(node.id) ||
        step.name === node.id
    )
}

function isRuntimeNodeId(nodeId: string): boolean {
    return nodeId.startsWith("runtime-run:") || nodeId.startsWith("runtime-group:") || nodeId.startsWith("runtime-event:")
}

function mapOrchestrationEventToExecutionStep(event: AgentExecutionEvent, index: number): ExecutionStep {
    const eventName = event.event || event.type || "event"
    const lifecycleStatus = String(event.data?.status || "")
    const joinStatus = String(event.data?.status || "")
    let status: ExecutionStep["status"] = "pending"

    if (eventName === "orchestration.child_lifecycle") {
        if (["failed", "cancelled", "timed_out", "error", "denied"].includes(lifecycleStatus)) {
            status = "error"
        } else if (["running", "queued", "paused", "pending"].includes(lifecycleStatus)) {
            status = "running"
        } else if (["completed", "completed_with_errors"].includes(lifecycleStatus)) {
            status = "completed"
        }
    } else if (eventName === "orchestration.join_decision") {
        if (!Boolean(event.data?.complete)) {
            status = "running"
        } else if (["failed", "timed_out", "cancelled", "error"].includes(joinStatus)) {
            status = "error"
        } else {
            status = "completed"
        }
    } else if (eventName === "orchestration.policy_deny") {
        status = "error"
    } else if (eventName === "orchestration.spawn_decision" || eventName === "orchestration.cancellation_propagation" || eventName === "node_end") {
        status = "completed"
    }

    return {
        id: `${eventName}:${event.span_id || event.run_id || "event"}:${index}`,
        name: event.name || eventName.replace("orchestration.", "").replaceAll("_", " "),
        type: "node",
        status,
        output: event.data,
        timestamp: new Date((event.received_at || Date.now()) + index),
    }
}

function isOrchestrationNodeType(nodeType: string): boolean {
    return ["spawn_run", "spawn_group", "join", "router", "judge", "replan", "cancel_subtree"].includes(nodeType)
}

function toStringList(value: unknown): string[] {
    if (!Array.isArray(value)) return []
    return value
        .map((item) => String(item ?? "").trim())
        .filter((item) => item.length > 0)
}

function validateNodePreflight(node: Node<AgentNodeData>): string[] {
    const config = ((node.data?.config || {}) as Record<string, unknown>)
    const nodeType = node.data?.nodeType || node.type
    const issues: string[] = []
    if (!isOrchestrationNodeType(String(nodeType || ""))) return issues

    if (nodeType === "spawn_run") {
        const hasTarget = Boolean(String(config.target_agent_slug || "").trim()) || Boolean(String(config.target_agent_id || "").trim())
        if (!hasTarget) issues.push("requires target agent")
        if (toStringList(config.scope_subset).length === 0) issues.push("requires scope subset")
    }
    if (nodeType === "spawn_group") {
        const targets = Array.isArray(config.targets) ? config.targets : []
        if (targets.length === 0) issues.push("requires at least one target")
        if (toStringList(config.scope_subset).length === 0) issues.push("requires scope subset")
        const joinMode = String(config.join_mode || "all")
        if (joinMode === "quorum") {
            const quorum = Number(config.quorum_threshold || 0)
            if (!Number.isInteger(quorum) || quorum < 1) issues.push("quorum threshold must be >= 1")
        }
    }
    if (nodeType === "join") {
        const mode = String(config.mode || "all")
        if (mode === "quorum") {
            const quorum = Number(config.quorum_threshold || 0)
            if (!Number.isInteger(quorum) || quorum < 1) issues.push("quorum threshold must be >= 1")
        }
    }
    if (nodeType === "judge") {
        const tableOutcomes = Array.isArray(config.route_table)
            ? config.route_table
                .map((item) => (item && typeof item === "object" ? String((item as Record<string, unknown>).name || "").trim() : ""))
                .filter(Boolean)
            : []
        const outcomes = tableOutcomes.length > 0
            ? tableOutcomes
            : (Array.isArray(config.outcomes) ? config.outcomes.filter((item) => typeof item === "string" && item.trim()) : [])
        if (outcomes.length < 2) issues.push("should define at least two outcomes")
    }
    return issues
}

function matchesEventToNode(event: AgentExecutionEvent, node: Node<AgentNodeData>, data: AgentNodeData): boolean {
    const config = (data.config || {}) as Record<string, unknown>
    const runtimeRunId = typeof config.run_id === "string" ? config.run_id : null
    const runtimeGroupId = typeof config.group_id === "string" ? config.group_id : null
    const sourceNodeId = typeof config.source_node_id === "string" ? config.source_node_id : null
    const eventData = event.data || {}

    if (event.span_id === node.id || (sourceNodeId && event.span_id === sourceNodeId)) {
        return true
    }

    if (runtimeRunId) {
        if (event.run_id === runtimeRunId) {
            return true
        }
        if (eventData.child_run_id === runtimeRunId) {
            return true
        }
        if (Array.isArray(eventData.cancelled_run_ids) && eventData.cancelled_run_ids.includes(runtimeRunId)) {
            return true
        }
    }

    if (runtimeGroupId) {
        if (eventData.group_id === runtimeGroupId || eventData.orchestration_group_id === runtimeGroupId) {
            return true
        }
    }

    if (typeof eventData.source_node_id === "string" && eventData.source_node_id === node.id) {
        return true
    }

    return false
}

function AgentBuilderInner({
    agentId,
    initialNodes = [],
    initialEdges = [],
    onSave,
    onCompile,
    onRun,
    isSaving = false,
    isCompiling = false,
}: AgentBuilderProps) {
    const reactFlowWrapper = useRef<HTMLDivElement>(null)
    const { screenToFlowPosition, getViewport, setViewport, getNodes, fitView } = useReactFlow()

    const normalizeNode = useCallback((node: Node) => normalizeBuilderNode(node), [])

    const normalizedInitialNodes = useMemo(() => {
        return (initialNodes || []).map((node) => {
            if (node.data && (node.data as AgentNodeData).category) {
                return node as Node<AgentNodeData>
            }
            return normalizeNode(node)
        })
    }, [initialNodes, normalizeNode])

    const normalizedInitialEdges = useMemo(() => normalizeBuilderEdges(initialEdges || []), [initialEdges])
    const [nodes, setNodes, onNodesChange] = useNodesState<Node<AgentNodeData>>(normalizedInitialNodes)
    const [edges, setEdges, onEdgesChange] = useEdgesState(normalizedInitialEdges)
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
    const [mode, setMode] = useState<"build" | "execute">("build")
    const [interactionMode, setInteractionMode] = useState<InteractionMode>("pan")
    const [isCatalogVisible, setIsCatalogVisible] = useState(true)

    useEffect(() => {
        setNodes((nds) => {
            let changed = false
            const normalized = nds.map((node) => {
                if (node.data && (node.data as AgentNodeData).category) {
                    return node
                }
                changed = true
                return normalizeNode(node)
            })
            return changed ? normalized : nds
        })
    }, [setNodes, normalizeNode])

    // Dedicated controller for execution (chat) mode
    const controller = useAgentRunController(agentId)
    const { executionSteps, executionEvents, currentRunId, currentRunStatus } = controller
    const runtimeOverlay = useAgentRuntimeGraph({
        staticNodes: nodes as Node<AgentNodeData>[],
        staticEdges: edges,
        runId: currentRunId,
        executionEvents,
        runStatus: currentRunStatus,
    })

    // History management using shared hook
    const {
        canUndo,
        canRedo,
        takeSnapshot,
        undo,
        redo,
    } = useBuilderHistory({ initialNodes: normalizedInitialNodes, initialEdges: normalizedInitialEdges })

    // Handle undo
    const handleUndo = useCallback(() => {
        const state = undo()
        if (state) {
            setNodes(state.nodes as Node<AgentNodeData>[])
            setEdges(state.edges)
        }
    }, [undo, setNodes, setEdges])

    // Handle redo
    const handleRedo = useCallback(() => {
        const state = redo()
        if (state) {
            setNodes(state.nodes as Node<AgentNodeData>[])
            setEdges(state.edges)
        }
    }, [redo, setNodes, setEdges])

    // Handle "push" animation when entering execute mode
    useEffect(() => {
        if (mode === "execute" && reactFlowWrapper.current) {
            const { x, y, zoom } = getViewport()
            const currentNodes = getNodes()
            if (currentNodes.length === 0) return

            const containerWidth = reactFlowWrapper.current.clientWidth
            const panelWidth = 400
            const availableWidth = containerWidth - panelWidth
            const targetScreenCenterX = availableWidth / 2

            // Calculate the bounding box of nodes in flow coordinates
            let minX = Infinity
            let maxX = -Infinity
            currentNodes.forEach(node => {
                const nodeWidth = node.measured?.width ?? 200
                minX = Math.min(minX, node.position.x)
                maxX = Math.max(maxX, node.position.x + nodeWidth)
            })

            const contentCenterFlowX = (minX + maxX) / 2
            const currentScreenCenterX = contentCenterFlowX * zoom + x
            const shift = targetScreenCenterX - currentScreenCenterX

            // Only shift if it's currently covered or too close to the panel
            // or if we want to ensure it's always centered for a premium feel
            setViewport({ x: x + shift, y, zoom }, { duration: 500 })
        }
    }, [mode, getViewport, setViewport, getNodes])

    // Auto-save on changes
    useEffect(() => {
        if (onSave && mode === "build") {
            onSave(nodes as Node<AgentNodeData>[], edges)
        }
    }, [nodes, edges, onSave, mode])

    // Update nodes with execution status
    useEffect(() => {
        if (mode !== "execute") {
            setNodes((nds) =>
                nds.map((node) => {
                    if (!node.data) return node
                    if (node.data.executionStatus) {
                        const rest = { ...node.data }
                        delete (rest as Record<string, unknown>).executionStatus
                        return { ...node, data: rest }
                    }
                    return node
                })
            )
            return
        }

        // console.log("[AgentBuilder] Execution Steps:", executionSteps)

        setNodes((nds) =>
            nds.map((node) => {
                if (!node.data) return node
                const data = node.data as AgentNodeData
                // Find steps matching this node by name or ID
                // Note: LangGraph nodes usually match the display name or a simplified version of it
                const nodeSteps = executionSteps.filter((step) => matchesStepToNode(step, node as Node<AgentNodeData>, data))

                if (nodeSteps.length === 0) return node

                // Get the latest status
                const latestStep = nodeSteps[nodeSteps.length - 1]
                const statusMap: Record<string, "pending" | "running" | "completed" | "failed"> = {
                    "pending": "pending",
                    "running": "running",
                    "completed": "completed",
                    "error": "failed"
                }
                const newStatus = statusMap[latestStep.status] || "pending"

                if (data.executionStatus !== newStatus) {
                    return {
                        ...node,
                        data: {
                            ...data,
                            executionStatus: newStatus,
                        },
                    }
                }
                return node
            })
        )
    }, [mode, executionSteps, setNodes])

    const renderNodes = useMemo(() => {
        return getRenderGraphForMode(
            mode,
            nodes as Node<AgentNodeData>[],
            edges,
            {
                runtimeNodes: runtimeOverlay.runtimeNodes,
                runtimeEdges: runtimeOverlay.runtimeEdges,
                runtimeStatusByNodeId: runtimeOverlay.runtimeStatusByNodeId,
                runtimeNotesByNodeId: runtimeOverlay.runtimeNotesByNodeId,
                takenStaticEdgeIds: runtimeOverlay.takenStaticEdgeIds,
            }
        ).nodes
    }, [mode, nodes, edges, runtimeOverlay.runtimeNodes, runtimeOverlay.runtimeEdges, runtimeOverlay.runtimeStatusByNodeId, runtimeOverlay.runtimeNotesByNodeId, runtimeOverlay.takenStaticEdgeIds])

    const renderEdges = useMemo(() => {
        return getRenderGraphForMode(
            mode,
            nodes as Node<AgentNodeData>[],
            edges,
            {
                runtimeNodes: runtimeOverlay.runtimeNodes,
                runtimeEdges: runtimeOverlay.runtimeEdges,
                runtimeStatusByNodeId: runtimeOverlay.runtimeStatusByNodeId,
                runtimeNotesByNodeId: runtimeOverlay.runtimeNotesByNodeId,
                takenStaticEdgeIds: runtimeOverlay.takenStaticEdgeIds,
            }
        ).edges
    }, [mode, nodes, edges, runtimeOverlay.runtimeNodes, runtimeOverlay.runtimeEdges, runtimeOverlay.runtimeStatusByNodeId, runtimeOverlay.runtimeNotesByNodeId, runtimeOverlay.takenStaticEdgeIds])

    const orchestrationPreflight = useMemo(() => {
        if (mode !== "build") return []
        return (nodes as Node<AgentNodeData>[])
            .filter((node) => isOrchestrationNodeType(String(node.data?.nodeType || node.type || "")))
            .map((node) => ({ node, issues: validateNodePreflight(node) }))
            .filter((item) => item.issues.length > 0)
    }, [mode, nodes])

    const selectedNode = renderNodes.find((n) => n.id === selectedNodeId) as
        | Node<AgentNodeData>
        | undefined

    const selectedNodeData: AgentNodeData | undefined = selectedNode?.data as AgentNodeData | undefined
    const safeSelectedNodeData: AgentNodeData | undefined = selectedNodeData ?? (selectedNode ? normalizeNode(selectedNode).data : undefined)
    const selectedNodeTraceSteps = useMemo(() => {
        if (!selectedNode || !safeSelectedNodeData) {
            return [] as ExecutionStep[]
        }

        const baseSteps = executionSteps.filter((step) =>
            matchesStepToNode(step, selectedNode as Node<AgentNodeData>, safeSelectedNodeData)
        )
        const orchestrationSteps = executionEvents
            .filter((event) => typeof event.event === "string" && event.event.startsWith("orchestration."))
            .filter((event) => matchesEventToNode(event, selectedNode as Node<AgentNodeData>, safeSelectedNodeData))
            .map((event, index) => mapOrchestrationEventToExecutionStep(event, index))

        const sortedSteps = [...baseSteps, ...orchestrationSteps].sort(
            (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
        )
        const nodeStatus = safeSelectedNodeData.executionStatus
        const terminalNodeStatus =
            nodeStatus === "completed" || nodeStatus === "failed"
                ? nodeStatus
                : null
        if (!terminalNodeStatus) {
            return sortedSteps
        }
        const expectedFinalStepStatus: ExecutionStep["status"] =
            terminalNodeStatus === "completed" ? "completed" : "error"
        const lastStep = sortedSteps[sortedSteps.length - 1]
        if (lastStep && lastStep.status === expectedFinalStepStatus) {
            return sortedSteps
        }
        const baseTime = lastStep?.timestamp?.getTime?.() || Date.now()
        return [
            ...sortedSteps,
            {
                id: `runtime-status:${selectedNode.id}:${terminalNodeStatus}`,
                name: "Runtime Status",
                type: "node",
                status: expectedFinalStepStatus,
                output: { status: terminalNodeStatus },
                timestamp: new Date(baseTime + 1),
            },
        ]
    }, [selectedNode, safeSelectedNodeData, executionSteps, executionEvents])

    const handleNodesChange = useCallback((changes: NodeChange<Node<AgentNodeData>>[]) => {
        if (mode !== "execute") {
            onNodesChange(changes)
            return
        }

        const staticChanges: NodeChange<Node<AgentNodeData>>[] = []
        const runtimeChanges: NodeChange<Node<AgentNodeData>>[] = []

        changes.forEach((change) => {
            if ("id" in change && isRuntimeNodeId(change.id)) {
                runtimeChanges.push(change)
                return
            }
            staticChanges.push(change)
        })

        if (staticChanges.length > 0) {
            onNodesChange(staticChanges)
        }
        if (runtimeChanges.length > 0) {
            runtimeOverlay.applyRuntimeNodeChanges(runtimeChanges)
        }
    }, [mode, onNodesChange, runtimeOverlay])

    const isValidConnection = useCallback(
        (connection: Edge | Connection) => {
            const sourceNode = nodes.find((n) => n.id === connection.source)
            const targetNode = nodes.find((n) => n.id === connection.target)

            if (!sourceNode || !targetNode) return false

            const sourceData = sourceNode.data as AgentNodeData
            const targetData = targetNode.data as AgentNodeData

            return canConnect(sourceData.outputType, targetData.inputType)
        },
        [nodes]
    )

    const onConnect = useCallback(
        (params: Connection) => {
            if (isValidConnection(params)) {
                setEdges((eds) => addEdge({
                    ...params,
                    id: `e-${nanoid(6)}`,
                    animated: true,
                    style: { stroke: "#6b7280", strokeWidth: 2 },
                }, eds))
                setTimeout(() => takeSnapshot(nodes as Node<AgentNodeData>[], edges), 0)
            }
        },
        [setEdges, isValidConnection, takeSnapshot, nodes, edges]
    )

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault()
        event.dataTransfer.dropEffect = "move"
    }, [])

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault()

            const nodeType = event.dataTransfer.getData("application/node-type") as AgentNodeType
            const category = event.dataTransfer.getData("application/node-category") as AgentNodeCategory
            const specString = event.dataTransfer.getData("application/node-spec")

            if (!nodeType || !category) return

            const spec = specString ? JSON.parse(specString) as AgentNodeSpec : getNodeSpec(nodeType)
            if (!spec) return

            const position = screenToFlowPosition({
                x: event.clientX,
                y: event.clientY,
            })

            const newNode: Node<AgentNodeData> = {
                id: `node-${nanoid(6)}`,
                type: nodeType,
                position,
                data: {
                    nodeType,
                    category,
                    displayName: spec.displayName,
                    config: {},
                    inputType: spec.inputType,
                    outputType: spec.outputType,
                    isConfigured: (spec.configFields || []).length === 0,
                    hasErrors: false,
                },
            }

            setNodes((nds) => [...nds, newNode])
            setTimeout(() => takeSnapshot([...nodes, newNode] as Node<AgentNodeData>[], edges), 0)
        },
        [screenToFlowPosition, setNodes, takeSnapshot, nodes, edges]
    )

    const handleDragStart = useCallback(
        (
            event: React.DragEvent,
            spec: AgentNodeSpec
        ) => {
            event.dataTransfer.setData("application/node-type", spec.nodeType)
            event.dataTransfer.setData("application/node-category", spec.category)
            event.dataTransfer.setData("application/node-spec", JSON.stringify(spec))
            event.dataTransfer.effectAllowed = "move"
        },
        []
    )

    const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
        setSelectedNodeId(node.id)
    }, [])

    const handlePaneClick = useCallback(() => {
        setSelectedNodeId(null)
    }, [])

    const handleConfigChange = useCallback(
        (nodeId: string, config: Record<string, unknown>) => {
            setNodes((nds) =>
                nds.map((node) => {
                    if (node.id === nodeId) {
                        const data = node.data as AgentNodeData
                        const spec = getNodeSpec(data.nodeType)
                        const requiredFields = spec?.configFields.filter(f => f.required) || []
                        const isConfigured = requiredFields.every((f) => {
                            const val = config[f.name]
                            if (Array.isArray(val)) {
                                return val.length > 0
                            }
                            return val !== undefined && val !== ""
                        })

                        return {
                            ...node,
                            data: {
                                ...data,
                                config,
                                isConfigured,
                            },
                        }
                    }
                    return node
                })
            )
        },
        [setNodes]
    )

    const handleClearCanvas = useCallback(() => {
        if (confirm("Are you sure you want to clear the canvas?")) {
            setNodes([])
            setEdges([])
            setTimeout(() => takeSnapshot([], []), 0)
        }
    }, [setNodes, setEdges, takeSnapshot])

    const handleAutoLayout = useCallback(() => {
        if (nodes.length === 0) return

        const layoutedNodes = computeAutoLayout(nodes, edges)
        setNodes(layoutedNodes)
        setIsCatalogVisible(false)

        setTimeout(() => {
            takeSnapshot(layoutedNodes as Node<AgentNodeData>[], edges)
            fitView({ padding: 0.2, duration: 300 })
        }, 0)
    }, [nodes, edges, setNodes, takeSnapshot, fitView])

    const handleOrganizeRuntime = useCallback(() => {
        if (runtimeOverlay.runtimeNodes.length === 0) return
        const layouted = computeAutoLayout(runtimeOverlay.runtimeNodes, runtimeOverlay.runtimeEdges)
        if (layouted.length === 0) return

        const currentMinX = Math.min(...runtimeOverlay.runtimeNodes.map((node) => node.position.x))
        const currentMinY = Math.min(...runtimeOverlay.runtimeNodes.map((node) => node.position.y))
        const layoutMinX = Math.min(...layouted.map((node) => node.position.x))
        const layoutMinY = Math.min(...layouted.map((node) => node.position.y))
        const offsetX = currentMinX - layoutMinX
        const offsetY = currentMinY - layoutMinY

        runtimeOverlay.setRuntimeNodes(
            layouted.map((node) => ({
                ...node,
                position: {
                    x: node.position.x + offsetX,
                    y: node.position.y + offsetY,
                },
                draggable: true,
                selectable: true,
                connectable: false,
            }))
        )

        setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 0)
    }, [runtimeOverlay, fitView])



    const handleCatalogToggle = useCallback(() => {
        if (mode === "execute") {
            setMode("build")
        }
        setIsCatalogVisible(true)
    }, [mode])

    return (
        <div className="relative flex h-full w-full overflow-hidden bg-background">
            {/* Header Center: Build/Execute Tabs */}
            {agentId && (
                <div className="absolute top-3 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 bg-background/95 backdrop-blur-md border rounded-xl p-1">
                    <button
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${mode === "build" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                            }`}
                        onClick={() => setMode("build")}
                    >
                        Build
                    </button>
                    <button
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${mode === "execute" ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                            }`}
                        onClick={() => {
                            setMode("execute")
                            setIsCatalogVisible(false)
                        }}
                    >
                        Execute
                    </button>
                </div>
            )}

            {/* Left Side Panels */}

            {/* 1. Build Mode: Catalog */}
            <FloatingPanel position="left" visible={isCatalogVisible && mode === "build"} className="w-64 z-40">
                <NodeCatalog
                    onDragStart={handleDragStart}
                    onClose={() => setIsCatalogVisible(false)}
                />
            </FloatingPanel>

            {/* 2. Execute Mode: Node Trace (Floating on the left) */}
            {mode === "execute" && selectedNode && safeSelectedNodeData && (
                <FloatingPanel
                    position="left"
                    visible={true}
                    autoHeight={true}
                    className="w-[320px] z-60"
                >
                    <NodeTracePanel
                        nodeId={selectedNode.id}
                        nodeName={safeSelectedNodeData.displayName}
                        steps={selectedNodeTraceSteps}
                        nodeStatus={safeSelectedNodeData.executionStatus as "pending" | "running" | "completed" | "failed" | "skipped" | undefined}
                        onClose={() => setSelectedNodeId(null)}
                    />
                </FloatingPanel>
            )}

            {/* Catalog Toggle Button */}
            <CatalogToggleButton
                visible={isCatalogVisible && mode === "build"}
                onClick={handleCatalogToggle}
                isExecutionMode={mode === "execute"}
            />

            {/* Canvas */}
            <div className="relative flex-1 bg-muted/40 rounded-2xl" ref={reactFlowWrapper}>
                {mode === "build" && orchestrationPreflight.length > 0 && (
                    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[55] w-[560px] max-w-[90%] rounded-xl border border-amber-300 bg-amber-50/95 backdrop-blur p-2">
                        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-800 mb-1">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            Orchestration preflight checks
                        </div>
                        <div className="space-y-1 max-h-[140px] overflow-auto">
                            {orchestrationPreflight.map(({ node, issues }) => (
                                <button
                                    key={`preflight-${node.id}`}
                                    className="w-full text-left text-[11px] text-amber-900 hover:bg-amber-100 rounded px-1.5 py-1"
                                    onClick={() => setSelectedNodeId(node.id)}
                                >
                                    <span className="font-semibold mr-1">{node.data?.displayName || node.id}:</span>
                                    {issues.join(", ")}
                                </button>
                            ))}
                        </div>
                    </div>
                )}
                <ReactFlow
                    nodes={renderNodes}
                    edges={renderEdges}
                    onNodesChange={handleNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={mode === "build" ? onConnect : undefined}
                    onDrop={mode === "build" ? onDrop : undefined}
                    onDragOver={mode === "build" ? onDragOver : undefined}
                    onNodeClick={handleNodeClick}
                    onPaneClick={handlePaneClick}
                    isValidConnection={isValidConnection}
                    nodeTypes={nodeTypes}
                    nodesDraggable={true}
                    nodesConnectable={mode === "build"}
                    defaultEdgeOptions={{
                        animated: true,
                        style: { stroke: "#6b7280", strokeWidth: 2 },
                    }}
                    panOnDrag={interactionMode === "pan"}
                    selectionOnDrag={interactionMode === "select"}
                    selectionMode={SelectionMode.Partial}
                    panOnScroll={interactionMode === "select"}
                    onNodeDragStop={mode === "build" ? () => setTimeout(() => takeSnapshot(nodes as Node<AgentNodeData>[], edges), 0) : undefined}
                    fitView
                    snapToGrid
                    snapGrid={[16, 16]}
                    className="bg-background"
                >
                    <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="opacity-0 " />

                    {/* Toolbar - only in build mode */}
                    {mode === "build" && (
                        <BuilderToolbar
                            interactionMode={interactionMode}
                            onModeChange={setInteractionMode}
                            canUndo={canUndo}
                            canRedo={canRedo}
                            onUndo={handleUndo}
                            onRedo={handleRedo}
                            onSave={onSave ? () => onSave(nodes as Node<AgentNodeData>[], edges) : undefined}
                            onCompile={onCompile}
                            onRun={onRun}
                            onAutoLayout={handleAutoLayout}
                            autoLayoutDisabled={nodes.length === 0}
                            onClear={handleClearCanvas}
                            isSaving={isSaving}
                            isCompiling={isCompiling}
                        />
                    )}

                    {/* Execute toolbar */}
                    {mode === "execute" && (
                        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 p-1.5 bg-background/90 backdrop-blur-md border rounded-2xl">
                            <ToolbarButton
                                icon={<LayoutGrid className="h-4 w-4" />}
                                onClick={handleOrganizeRuntime}
                                disabled={runtimeOverlay.runtimeNodes.length === 0}
                                title="Organize Overlay"
                            />
                            <ToolbarButton
                                icon={<Trash2 className="h-4 w-4" />}
                                onClick={() => runtimeOverlay.clearRuntimeOverlay()}
                                variant="destructive"
                                disabled={runtimeOverlay.runtimeNodes.length === 0 && runtimeOverlay.runtimeEdges.length === 0}
                                title="Clear Overlay"
                            />
                        </div>
                    )}

                    <div className="absolute bottom-6 right-6">
                        <Controls className="static! flex! flex-row! gap-1! bg-transparent! border-none! shadow-none!" />
                    </div>
                </ReactFlow>
            </div>

            {/* Right Side Panels */}

            {/* 1. Execution Mode: Always show Chat */}
            {mode === "execute" && agentId && (
                <FloatingPanel position="right" visible={true} className="w-[400px]" fullHeight={false}>
                    <ExecutionPanel controller={controller} />
                </FloatingPanel>
            )}

            {/* 3. Build Mode: Show Config Panel if node is selected */}
            {mode === "build" && selectedNode && safeSelectedNodeData && (
                <FloatingPanel position="right" visible={true} className="w-[400px]" autoHeight={true}>
                    <ConfigPanel
                        key={selectedNode.id}
                        nodeId={selectedNode.id}
                        data={safeSelectedNodeData}
                        onConfigChange={handleConfigChange}
                        onClose={() => setSelectedNodeId(null)}
                        availableVariables={[
                            // Flatten input and state variables from Start node
                            ...((nodes.find(n => n.type === "start")?.data?.config?.input_variables as any[]) || []),
                            ...((nodes.find(n => n.type === "start")?.data?.config?.state_variables as any[]) || [])
                        ]}
                    />
                </FloatingPanel>
            )}
        </div>
    )
}

export function AgentBuilder(props: AgentBuilderProps) {
    return (
        <ReactFlowProvider>
            <AgentBuilderInner {...props} />
        </ReactFlowProvider>
    )
}

function computeAutoLayout<T extends Record<string, unknown>>(nodes: Node<T>[], edges: Edge[]) {
    const nodeSpacing = 140
    const rankSpacing = 280
    const startX = 40
    const startY = 40

    const indegree = new Map<string, number>()
    const outgoing = new Map<string, string[]>()

    nodes.forEach((node) => {
        indegree.set(node.id, 0)
        outgoing.set(node.id, [])
    })

    edges.forEach((edge) => {
        if (!edge.source || !edge.target) return
        if (!indegree.has(edge.target)) return
        indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1)
        const list = outgoing.get(edge.source) || []
        list.push(edge.target)
        outgoing.set(edge.source, list)
    })

    const ranks = new Map<string, number>()
    const queue: string[] = []

    indegree.forEach((count, id) => {
        if (count === 0) queue.push(id)
    })

    while (queue.length) {
        const current = queue.shift()
        if (!current) continue
        const currentRank = ranks.get(current) ?? 0
        const neighbors = outgoing.get(current) || []
        neighbors.forEach((target) => {
            const nextRank = currentRank + 1
            const existing = ranks.get(target)
            ranks.set(target, existing !== undefined ? Math.max(existing, nextRank) : nextRank)
            const nextIndegree = (indegree.get(target) || 0) - 1
            indegree.set(target, nextIndegree)
            if (nextIndegree === 0) {
                queue.push(target)
            }
        })
    }

    nodes.forEach((node) => {
        if (!ranks.has(node.id)) {
            ranks.set(node.id, 0)
        }
    })

    const grouped = new Map<number, Node<T>[]>()
    nodes.forEach((node) => {
        const rank = ranks.get(node.id) ?? 0
        const list = grouped.get(rank) || []
        list.push(node)
        grouped.set(rank, list)
    })

    const sortedRanks = Array.from(grouped.keys()).sort((a, b) => a - b)

    const layoutedNodes: Node<T>[] = []
    sortedRanks.forEach((rank) => {
        const row = grouped.get(rank) || []
        row.sort((a, b) => (a.position.y - b.position.y) || a.id.localeCompare(b.id))

        row.forEach((node, index) => {
            layoutedNodes.push({
                ...node,
                position: {
                    x: startX + rank * rankSpacing,
                    y: startY + index * nodeSpacing,
                },
            })
        })
    })

    return layoutedNodes
}
