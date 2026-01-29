"use client"

import { useCallback, useState, useRef, useEffect } from "react"
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
import { useAgentRunController } from "@/hooks/useAgentRunController"
import {
    FloatingPanel,
    BuilderToolbar,
    CatalogToggleButton,
    useBuilderHistory,
    InteractionMode,
} from "@/components/builder"
import {
    AgentNodeData,
    AgentNodeCategory,
    AgentNodeType,
    canConnect,
    getNodeSpec,
} from "./types"

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
    const { screenToFlowPosition, getViewport, setViewport, getNodes } = useReactFlow()

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
    const [mode, setMode] = useState<"build" | "execute">("build")
    const [interactionMode, setInteractionMode] = useState<InteractionMode>("pan")
    const [isCatalogVisible, setIsCatalogVisible] = useState(true)

    // Dedicated controller for execution (chat) mode
    const controller = useAgentRunController(agentId)
    const { executionSteps } = controller

    // History management using shared hook
    const {
        canUndo,
        canRedo,
        takeSnapshot,
        undo,
        redo,
    } = useBuilderHistory({ initialNodes, initialEdges })

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

    // Auto-toggle catalog on mode change (force close in execute mode)
    useEffect(() => {
        if (mode === "execute") {
            setIsCatalogVisible(false)
        }
    }, [mode])

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
                    if (node.data.executionStatus) {
                        const { executionStatus, ...rest } = node.data
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
                const data = node.data as AgentNodeData
                // Find steps matching this node by name or ID
                // Note: LangGraph nodes usually match the display name or a simplified version of it
                const nodeSteps = executionSteps.filter(s => {
                    // console.log(`[AgentBuilder] Checking node ${node.id} (${data.displayName}) against step ${s.name} (${s.id})`)
                    return s.name === data.displayName ||
                        s.name.toLowerCase() === data.nodeType.toLowerCase() ||
                        s.id.includes(node.id) ||
                        s.name === node.id
                })

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

    const selectedNode = nodes.find((n) => n.id === selectedNodeId) as
        | Node<AgentNodeData>
        | undefined

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

            if (!nodeType || !category) return

            const spec = getNodeSpec(nodeType)
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
                    isConfigured: spec.configFields.length === 0,
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
            nodeType: AgentNodeType,
            category: AgentNodeCategory
        ) => {
            event.dataTransfer.setData("application/node-type", nodeType)
            event.dataTransfer.setData("application/node-category", category)
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



    const handleCatalogToggle = useCallback(() => {
        if (mode === "execute") {
            setMode("build")
        }
        setIsCatalogVisible(true)
    }, [mode])

    return (
        <div className="relative flex h-full w-full overflow-hidden bg-background">
            {/* Left Side Panels */}

            {/* 1. Build Mode: Catalog */}
            <FloatingPanel position="left" visible={isCatalogVisible && mode === "build"} className="w-64 z-60">
                <NodeCatalog
                    onDragStart={handleDragStart}
                    onClose={() => setIsCatalogVisible(false)}
                />
            </FloatingPanel>

            {/* 2. Execute Mode: Node Trace (Floating on the left) */}
            {mode === "execute" && selectedNode && (
                <FloatingPanel
                    position="left"
                    visible={true}
                    autoHeight={true}
                    className="w-[320px] z-60"
                >
                    <NodeTracePanel
                        nodeId={selectedNode.id}
                        nodeName={selectedNode.data.displayName}
                        steps={executionSteps.filter(s =>
                            s.name === selectedNode.data.displayName ||
                            s.name.toLowerCase() === selectedNode.data.nodeType.toLowerCase() ||
                            s.id.includes(selectedNode.id) ||
                            s.name === selectedNode.id
                        )}
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
            <div className="relative flex-1 bg-muted/40" ref={reactFlowWrapper}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onNodeClick={handleNodeClick}
                    onPaneClick={handlePaneClick}
                    isValidConnection={isValidConnection}
                    nodeTypes={nodeTypes}
                    defaultEdgeOptions={{
                        animated: true,
                        style: { stroke: "#6b7280", strokeWidth: 2 },
                    }}
                    panOnDrag={interactionMode === "pan"}
                    selectionOnDrag={interactionMode === "select"}
                    selectionMode={SelectionMode.Partial}
                    panOnScroll={interactionMode === "select"}
                    onNodeDragStop={() => setTimeout(() => takeSnapshot(nodes as Node<AgentNodeData>[], edges), 0)}
                    fitView
                    snapToGrid
                    snapGrid={[16, 16]}
                    className="bg-transparent"
                >
                    <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="opacity-100" />

                    {/* Mode Toggle Pills */}
                    {agentId && (
                        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 bg-background/90 backdrop-blur-md border rounded-xl p-1">
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
                                onClick={() => setMode("execute")}
                            >
                                Execute
                            </button>
                        </div>
                    )}

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
                            onClear={handleClearCanvas}
                            isSaving={isSaving}
                            isCompiling={isCompiling}
                        />
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
            {mode === "build" && selectedNode && (
                <FloatingPanel position="right" visible={true} className="w-[400px]" autoHeight={true}>
                    <ConfigPanel
                        key={selectedNode.id}
                        nodeId={selectedNode.id}
                        data={selectedNode.data}
                        onConfigChange={handleConfigChange}
                        onClose={() => setSelectedNodeId(null)}
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
