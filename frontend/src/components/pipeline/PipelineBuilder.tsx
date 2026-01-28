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
import {
  Trash2,
  Undo2,
  Redo2,
  MousePointer2,
  Hand,
  Save,
  Zap,
  Play,
  Loader2,
  LayoutPanelLeft,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { nodeTypes } from "./nodes"
import { NodeCatalog } from "./NodeCatalog"
import { ConfigPanel } from "./ConfigPanel"
import { cn } from "@/lib/utils"
import {
  PipelineNodeData,
  OperatorCategory,
  OperatorSpec,
  DataType,
  canConnect,
} from "./types"

type OperatorCatalog = Record<string, Array<{
  operator_id: string
  display_name: string
  input_type: DataType
  output_type: DataType
  dimension?: number
}>>

import { PipelineStepExecution } from "./types"
import { ExecutionDetailsPanel } from "./ExecutionDetailsPanel"
import { ExecutionDetailsSkeleton } from "./ExecutionDetailsSkeleton"

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

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [interactionMode, setInteractionMode] = useState<'pan' | 'select'>('pan')

  // History state
  const [history, setHistory] = useState<{ nodes: Node<PipelineNodeData>[]; edges: Edge[] }[]>([
    { nodes: initialNodes as Node<PipelineNodeData>[], edges: initialEdges }
  ])
  const [historyIndex, setHistoryIndex] = useState(0)


  // Update nodes with execution status (or clear when exiting execution mode)
  useEffect(() => {
    // Clear execution status when not in execution mode
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

  const takeSnapshot = useCallback(() => {
    const nextState = { nodes: [...nodes] as Node<PipelineNodeData>[], edges: [...edges] }
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
  }, [nodes, edges, historyIndex])

  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const prevState = history[historyIndex - 1]
      setNodes(prevState.nodes)
      setEdges(prevState.edges)
      setHistoryIndex(historyIndex - 1)
    }
  }, [history, historyIndex, setNodes, setEdges])

  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextState = history[historyIndex + 1]
      setNodes(nextState.nodes)
      setEdges(nextState.edges)
      setHistoryIndex(historyIndex + 1)
    }
  }, [history, historyIndex, setNodes, setEdges])

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
        setTimeout(takeSnapshot, 0)
      }
    },
    [setEdges, isValidConnection, takeSnapshot]
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
      setTimeout(takeSnapshot, 0)
    },
    [catalog, screenToFlowPosition, setNodes, takeSnapshot]
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

  const clearCanvas = useCallback(() => {
    if (confirm("Are you sure you want to clear the canvas?")) {
      setNodes([])
      setEdges([])
      setTimeout(takeSnapshot, 0)
    }
  }, [setNodes, setEdges, takeSnapshot])

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-background">
      {/* Floating Operator Catalog Bubble - with sliding animation */}
      <div
        className={cn(
          "absolute left-3 top-3 bottom-3 w-64 z-40 transition-all duration-500 ease-in-out",
          !isCatalogVisible ? "-translate-x-[calc(100%+24px)]" : "translate-x-0"
        )}
      >
        <div className="relative h-full rounded-2xl border bg-background/95 backdrop-blur-md flex flex-col overflow-hidden">
          <NodeCatalog
            catalog={catalog}
            onDragStart={handleDragStart}
            onAddCustomOperator={onAddCustomOperator}
            onClose={() => setIsCatalogVisible(false)}
          />
        </div>
      </div>

      {/* Toggle Button when catalog is hidden */}
      {!isCatalogVisible && (
        <div className="absolute left-3 top-3 z-50">
          <Button
            variant="outline"
            size="icon"
            className="h-10 w-10 rounded-xl shadow-none backdrop-blur-md border hover:bg-muted"
            onClick={() => {
              if (isExecutionMode && onExitExecutionMode) {
                onExitExecutionMode()
              }
              setIsCatalogVisible(true)
            }}
            title={isExecutionMode ? "Exit Execution Mode" : "Show Catalog"}
          >
            <LayoutPanelLeft className="h-4 w-4" />
          </Button>
        </div>
      )}

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
            // Trigger fitView after the flow is fully initialized to ensure edges render correctly
            setTimeout(() => instance.fitView(), 50)
          }}
          panOnDrag={interactionMode === 'pan'}
          selectionOnDrag={interactionMode === 'select'}
          selectionMode={SelectionMode.Partial}
          panOnScroll={interactionMode === 'select'}
          onNodeDragStop={() => setTimeout(takeSnapshot, 0)}
          fitView
          className="bg-transparent"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            className="opacity-100"
          />

          {/* Custom Bottom Controls - Shadow Removed */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 p-1.5 bg-background/90 backdrop-blur-md border rounded-2xl">

            <Button
              variant="ghost"
              size="icon"
              className={cn("rounded-xl h-10 w-10", interactionMode === 'pan' && "bg-muted")}
              onClick={() => setInteractionMode('pan')}
              title="Pan Tool"
            >
              <Hand className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className={cn("rounded-xl h-10 w-10", interactionMode === 'select' && "bg-muted")}
              onClick={() => setInteractionMode('select')}
              title="Selection Tool"
            >
              <MousePointer2 className="h-4 w-4" />
            </Button>

            <Separator orientation="vertical" className="h-6" />

            <Button
              variant="ghost"
              size="icon"
              className="rounded-xl h-10 w-10"
              onClick={undo}
              disabled={historyIndex <= 0}
              title="Undo"
            >
              <Undo2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="rounded-xl h-10 w-10"
              onClick={redo}
              disabled={historyIndex >= history.length - 1}
              title="Redo"
            >
              <Redo2 className="h-4 w-4" />
            </Button>

            <Separator orientation="vertical" className="h-6" />

            {onSave && (
              <Button
                variant="ghost"
                size="icon"
                className="rounded-xl h-10 w-10 text-blue-500 hover:text-blue-600 hover:bg-blue-500/10"
                onClick={() => onSave(nodes as Node<PipelineNodeData>[], edges)}
                disabled={isSaving}
                title="Save Pipeline"
              >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              </Button>
            )}

            {onCompile && (
              <Button
                variant="ghost"
                size="icon"
                className="rounded-xl h-10 w-10 text-orange-500 hover:text-orange-600 hover:bg-orange-500/10"
                onClick={onCompile}
                disabled={isCompiling}
                title="Compile Pipeline"
              >
                {isCompiling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
              </Button>
            )}

            {onRun && (
              <Button
                variant="ghost"
                size="icon"
                className="rounded-xl h-10 w-10 text-green-500 hover:text-green-600 hover:bg-green-500/10"
                onClick={onRun}
                title="Run Pipeline"
              >
                <Play className="h-4 w-4" />
              </Button>
            )}

            <Separator orientation="vertical" className="h-6" />

            <Button
              variant="ghost"
              size="icon"
              className="rounded-xl h-10 w-10 text-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={clearCanvas}
              title="Clear Canvas"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>

          <div className="absolute bottom-6 right-6">
            <Controls className="static! flex! flex-row! gap-1! bg-transparent! border-none! shadow-none!" />
          </div>
        </ReactFlow>
      </div>

      {/* Floating Configuration Bubble or Execution Details */}
      {(selectedNode || selectedStepExecution) && (
        <div className="absolute right-3 top-3 bottom-3 w-[400px] z-40 flex flex-col pointer-events-none">
          <div className="h-full border rounded-2xl bg-background/95 backdrop-blur-md flex flex-col overflow-hidden pointer-events-auto">
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
          </div>
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
