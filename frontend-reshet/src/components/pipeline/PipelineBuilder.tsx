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
import { ExecutionDetailsPanel } from "./ExecutionDetailsPanel"
import { ExecutionDetailsSkeleton } from "./ExecutionDetailsSkeleton"
import {
  FloatingPanel,
  BuilderToolbar,
  CatalogToggleButton,
  useBuilderHistory,
  InteractionMode,
} from "@/components/builder"
import {
  PipelineNodeData,
  OperatorCategory,
  OperatorSpec,
  DataType,
  canConnect,
  PipelineStepExecution,
} from "./types"

type OperatorCatalog = Record<string, Array<{
  operator_id: string
  display_name: string
  input_type: DataType
  output_type: DataType
  dimension?: number
}>>

interface PipelineBuilderProps {
  catalog: OperatorCatalog
  operatorSpecs: Record<string, OperatorSpec>
  initialNodes?: Node<PipelineNodeData>[]
  initialEdges?: Edge[]
  onChange?: (nodes: Node<PipelineNodeData>[], edges: Edge[]) => void
  onSave?: (nodes: Node<PipelineNodeData>[], edges: Edge[]) => void
  onAddCustomOperator?: () => void
  onCompile?: () => void
  onRun?: () => void
  pipelineType?: "ingestion" | "retrieval"
  isSaving?: boolean
  isCompiling?: boolean
  executionSteps?: Record<string, PipelineStepExecution>
  isExecutionMode?: boolean
  onExitExecutionMode?: () => void
}

function PipelineBuilderInner({
  catalog,
  operatorSpecs,
  initialNodes = [],
  initialEdges = [],
  onChange,
  onSave,
  onAddCustomOperator,
  onCompile,
  onRun,
  pipelineType = "ingestion",
  isSaving = false,
  isCompiling = false,
  executionSteps,
  isExecutionMode = false,
  onExitExecutionMode,
}: PipelineBuilderProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [isCatalogVisible, setIsCatalogVisible] = useState(!isExecutionMode)
  const [prevExecutionMode, setPrevExecutionMode] = useState(isExecutionMode)

  if (prevExecutionMode !== isExecutionMode) {
    setPrevExecutionMode(isExecutionMode)
    setIsCatalogVisible(!isExecutionMode)
  }

  const { screenToFlowPosition } = useReactFlow()

  const sanitizedInitialNodes = useMemo(() => {
    return initialNodes.map(node => {
      if (node.type === "input" || node.type === "output") {
        return { ...node, type: `pipeline_${node.type}` }
      }
      return node
    })
  }, [initialNodes])

  const [nodes, setNodes, onNodesChange] = useNodesState(sanitizedInitialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('pan')

  // Use shared history hook
  const {
    canUndo,
    canRedo,
    takeSnapshot,
    undo,
    redo,
  } = useBuilderHistory({ initialNodes, initialEdges })

  const handleUndo = useCallback(() => {
    const state = undo()
    if (state) {
      setNodes(state.nodes as Node<PipelineNodeData>[])
      setEdges(state.edges)
    }
  }, [undo, setNodes, setEdges])

  const handleRedo = useCallback(() => {
    const state = redo()
    if (state) {
      setNodes(state.nodes as Node<PipelineNodeData>[])
      setEdges(state.edges)
    }
  }, [redo, setNodes, setEdges])

  // Update nodes with execution status (or clear when exiting execution mode)
  useEffect(() => {
    if (!isExecutionMode) {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.data.executionStatus) {
            const rest = { ...node.data }
            delete rest.executionStatus
            return { ...node, data: rest }
          }
          return node
        })
      )
      return
    }

    if (!executionSteps) return

    setNodes((nds) =>
      nds.map((node) => {
        const step = executionSteps[node.id]
        if (step && node.data.executionStatus !== step.status) {
          return {
            ...node,
            data: {
              ...node.data,
              executionStatus: step.status,
            },
          }
        }
        return node
      })
    )
  }, [isExecutionMode, executionSteps, setNodes])

  useEffect(() => {
    if (onChange) {
      onChange(nodes as Node<PipelineNodeData>[], edges)
    }
  }, [nodes, edges, onChange])

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) as
    | Node<PipelineNodeData>
    | undefined

  const selectedStepExecution = selectedNodeId && executionSteps ? executionSteps[selectedNodeId] : null

  const isValidConnection = useCallback(
    (connection: Edge | Connection) => {
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
        setEdges((eds) => {
          const newEdges = addEdge({ ...params, id: `e-${nanoid(6)}`, animated: true }, eds)
          return newEdges
        })
        setTimeout(() => takeSnapshot(nodes as Node<PipelineNodeData>[], edges), 0)
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

      const operatorId = event.dataTransfer.getData("application/operator-id")
      const category = event.dataTransfer.getData(
        "application/operator-category"
      ) as OperatorCategory

      if (!operatorId || !category) return

      const categoryItems = catalog[category]
      if (!categoryItems) return

      const catalogItem = categoryItems.find(
        (item: any) => item.operator_id === operatorId
      )

      if (!catalogItem) return

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const nodeType = category === "input" || category === "output" ? `pipeline_${category}` : category

      const newNode: Node<PipelineNodeData> = {
        id: `node-${nanoid(6)}`,
        type: nodeType,
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
      setTimeout(() => takeSnapshot([...nodes, newNode] as Node<PipelineNodeData>[], edges), 0)
    },
    [catalog, screenToFlowPosition, setNodes, takeSnapshot, nodes, edges]
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

  const handleClearCanvas = useCallback(() => {
    if (confirm("Are you sure you want to clear the canvas?")) {
      setNodes([])
      setEdges([])
      setTimeout(() => takeSnapshot([], []), 0)
    }
  }, [setNodes, setEdges, takeSnapshot])

  const handleCatalogToggle = useCallback(() => {
    if (isExecutionMode && onExitExecutionMode) {
      onExitExecutionMode()
    }
    setIsCatalogVisible(true)
  }, [isExecutionMode, onExitExecutionMode])

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-background">
      {/* Floating Operator Catalog using shared component */}
      <FloatingPanel position="left" visible={isCatalogVisible} className="w-64 z-40">
        <NodeCatalog
          catalog={catalog}
          onDragStart={handleDragStart}
          onAddCustomOperator={onAddCustomOperator}
          onClose={() => setIsCatalogVisible(false)}
          pipelineType={pipelineType}
        />
      </FloatingPanel>

      {/* Catalog Toggle Button */}
      <CatalogToggleButton
        visible={isCatalogVisible}
        onClick={handleCatalogToggle}
        isExecutionMode={isExecutionMode}
      />

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
          defaultEdgeOptions={{ animated: true }}
          onInit={(instance) => {
            setTimeout(() => instance.fitView(), 50)
          }}
          panOnDrag={interactionMode === 'pan'}
          selectionOnDrag={interactionMode === 'select'}
          selectionMode={SelectionMode.Partial}
          panOnScroll={interactionMode === 'select'}
          onNodeDragStop={() => setTimeout(() => takeSnapshot(nodes as Node<PipelineNodeData>[], edges), 0)}
          fitView
          className="bg-transparent"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            className="opacity-100"
          />

          {/* Shared Toolbar Component */}
          <BuilderToolbar
            interactionMode={interactionMode}
            onModeChange={setInteractionMode}
            canUndo={canUndo}
            canRedo={canRedo}
            onUndo={handleUndo}
            onRedo={handleRedo}
            onSave={onSave ? () => onSave(nodes as Node<PipelineNodeData>[], edges) : undefined}
            onCompile={onCompile}
            onRun={onRun}
            onClear={handleClearCanvas}
            isSaving={isSaving}
            isCompiling={isCompiling}
          />

          <div className="absolute bottom-6 right-6">
            <Controls className="static! flex! flex-row! gap-1! bg-transparent! border-none! shadow-none!" />
          </div>
        </ReactFlow>
      </div>

      {/* Floating Configuration/Execution Panel using shared component */}
      {(selectedNode || selectedStepExecution) && (
        <FloatingPanel position="right" visible={true} className="w-[400px]">
          {selectedStepExecution ? (
            <ExecutionDetailsPanel
              step={selectedStepExecution}
              onClose={() => setSelectedNodeId(null)}
            />
          ) : isExecutionMode && selectedNode ? (
            <ExecutionDetailsSkeleton onClose={() => setSelectedNodeId(null)} />
          ) : selectedNode ? (
            <ConfigPanel
              key={selectedNode.id}
              nodeId={selectedNode.id}
              data={selectedNode.data}
              operatorSpec={operatorSpecs[selectedNode.data.operator]}
              onConfigChange={handleConfigChange}
              onClose={() => setSelectedNodeId(null)}
            />
          ) : null}
        </FloatingPanel>
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
