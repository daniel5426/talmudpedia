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
  PipelineNodeData,
  OperatorCategory,
  OperatorSpec,
  DataType,
  canConnect,
} from "./types"

interface OperatorCatalog {
  source: Array<{
    operator_id: string
    display_name: string
    input_type: DataType
    output_type: DataType
    dimension?: number
  }>
  transform: Array<{
    operator_id: string
    display_name: string
    input_type: DataType
    output_type: DataType
    dimension?: number
  }>
  embedding: Array<{
    operator_id: string
    display_name: string
    input_type: DataType
    output_type: DataType
    dimension?: number
  }>
  storage: Array<{
    operator_id: string
    display_name: string
    input_type: DataType
    output_type: DataType
    dimension?: number
  }>
}

interface PipelineBuilderProps {
  catalog: OperatorCatalog
  operatorSpecs: Record<string, OperatorSpec>
  initialNodes?: Node<PipelineNodeData>[]
  initialEdges?: Edge[]
  onSave?: (nodes: Node<PipelineNodeData>[], edges: Edge[]) => void
}

function PipelineBuilderInner({
  catalog,
  operatorSpecs,
  initialNodes = [],
  initialEdges = [],
  onSave,
}: PipelineBuilderProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition } = useReactFlow()

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  useEffect(() => {
    if (onSave) {
      onSave(nodes as Node<PipelineNodeData>[], edges)
    }
  }, [nodes, edges, onSave])

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) as
    | Node<PipelineNodeData>
    | undefined

  const isValidConnection = useCallback(
    (connection: Connection) => {
      const sourceNode = nodes.find((n) => n.id === connection.source)
      const targetNode = nodes.find((n) => n.id === connection.target)

      if (!sourceNode || !targetNode) return false

      const sourceData = sourceNode.data as PipelineNodeData
      const targetData = targetNode.data as PipelineNodeData

      return canConnect(sourceData.outputType, targetData.inputType)
    },
    [nodes]
  )

  const onConnect = useCallback(
    (params: Connection) => {
      if (isValidConnection(params)) {
        setEdges((eds) => addEdge({ ...params, id: `e-${nanoid(6)}` }, eds))
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

      const operatorId = event.dataTransfer.getData("application/operator-id")
      const category = event.dataTransfer.getData(
        "application/operator-category"
      ) as OperatorCategory

      if (!operatorId || !category) return

      const catalogItem = catalog[category]?.find(
        (item) => item.operator_id === operatorId
      )

      if (!catalogItem) return

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const newNode: Node<PipelineNodeData> = {
        id: `node-${nanoid(6)}`,
        type: category,
        position,
        data: {
          operator: operatorId,
          category,
          displayName: catalogItem.display_name,
          config: {},
          inputType: catalogItem.input_type,
          outputType: catalogItem.output_type,
          isConfigured: false,
          hasErrors: false,
        },
      }

      setNodes((nds) => [...nds, newNode])
    },
    [catalog, screenToFlowPosition, setNodes]
  )

  const handleDragStart = useCallback(
    (
      event: React.DragEvent,
      operatorId: string,
      category: OperatorCategory
    ) => {
      event.dataTransfer.setData("application/operator-id", operatorId)
      event.dataTransfer.setData("application/operator-category", category)
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
            const data = node.data as PipelineNodeData
            const spec = operatorSpecs[data.operator]
            const requiredFields = spec?.required_config || []
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
    [setNodes, operatorSpecs]
  )

  return (
    <div className="flex h-full w-full">
      <div className="w-64 border-r bg-muted/30 shrink-0">
        <NodeCatalog catalog={catalog} onDragStart={handleDragStart} />
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
            operatorSpec={operatorSpecs[selectedNode.data.operator]}
            onConfigChange={handleConfigChange}
            onClose={() => setSelectedNodeId(null)}
          />
        </div>
      )}
    </div>
  )
}

export function PipelineBuilder(props: PipelineBuilderProps) {
  return (
    <ReactFlowProvider>
      <PipelineBuilderInner {...props} />
    </ReactFlowProvider>
  )
}
