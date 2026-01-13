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
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { nanoid } from "nanoid"
import { nodeTypes } from "./nodes"
import { NodeCatalog } from "./NodeCatalog"
import { ConfigPanel } from "./ConfigPanel"
import {
    AgentNodeData,
    AgentNodeCategory,
    AgentNodeType,
    canConnect,
    getNodeSpec,
    AGENT_NODE_SPECS,
} from "./types"

interface AgentBuilderProps {
    initialNodes?: Node<AgentNodeData>[]
    initialEdges?: Edge[]
    onSave?: (nodes: Node<AgentNodeData>[], edges: Edge[]) => void
}

function AgentBuilderInner({
    initialNodes = [],
    initialEdges = [],
    onSave,
}: AgentBuilderProps) {
    const reactFlowWrapper = useRef<HTMLDivElement>(null)
    const { screenToFlowPosition } = useReactFlow()

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

    // Auto-save on changes
    useEffect(() => {
        if (onSave) {
            onSave(nodes as Node<AgentNodeData>[], edges)
        }
    }, [nodes, edges, onSave])

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
            }
        },
        [setEdges, isValidConnection]
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
                    isConfigured: spec.configFields.length === 0, // No config needed = auto-configured
                    hasErrors: false,
                },
            }

            setNodes((nds) => [...nds, newNode])
        },
        [screenToFlowPosition, setNodes]
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

    return (
        <div className="flex h-full w-full">
            <div className="w-64 border-r bg-muted/30 shrink-0">
                <NodeCatalog onDragStart={handleDragStart} />
            </div>

            <div className="flex-1" ref={reactFlowWrapper}>
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
                    fitView
                    snapToGrid
                    snapGrid={[16, 16]}
                    className="bg-background"
                    defaultEdgeOptions={{
                        animated: true,
                        style: { stroke: "#6b7280", strokeWidth: 2 },
                    }}
                >
                    <Controls />
                    <Background gap={16} size={1} />
                </ReactFlow>
            </div>

            {selectedNode && (
                <div className="w-80 shrink-0">
                    <ConfigPanel
                        nodeId={selectedNode.id}
                        data={selectedNode.data}
                        onConfigChange={handleConfigChange}
                        onClose={() => setSelectedNodeId(null)}
                    />
                </div>
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
