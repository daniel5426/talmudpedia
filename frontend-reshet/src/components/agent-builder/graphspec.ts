import { Edge, Node } from "@xyflow/react"

import { AgentNodeData, AgentNodeType, getNodeSpec } from "./types"

const ORCHESTRATION_V2_NODE_TYPES = new Set<AgentNodeType>([
    "spawn_run",
    "spawn_group",
    "join",
    "router",
    "judge",
    "replan",
    "cancel_subtree",
])

interface GraphSpecNormalizeOptions {
    specVersion?: string
}

export function normalizeBuilderNode(node: Node): Node<AgentNodeData> {
    const raw: any = node as any
    const existing = (raw.data || {}) as Partial<AgentNodeData>
    const nodeType = (raw.type || raw.nodeType || existing.nodeType || "transform") as AgentNodeType
    const spec = getNodeSpec(nodeType)
    const rawConfig = raw.config ?? {}
    const existingConfig = existing.config ?? {}
    const config = { ...rawConfig, ...existingConfig }
    const resolvedInputMappings = existing.inputMappings ?? raw.input_mappings
    if (resolvedInputMappings && !("input_mappings" in config)) {
        config["input_mappings"] = resolvedInputMappings
    }
    const category =
        existing.category ??
        spec?.category ??
        (typeof nodeType === "string" && nodeType.startsWith("artifact:") ? "action" : "data")
    const displayName =
        existing.displayName ??
        spec?.displayName ??
        (config?.label as string) ??
        nodeType
    const inputType = existing.inputType ?? spec?.inputType ?? "any"
    const outputType = existing.outputType ?? spec?.outputType ?? "any"

    return {
        ...node,
        type: nodeType,
        data: {
            ...existing,
            nodeType,
            category,
            displayName,
            config,
            inputType,
            outputType,
            isConfigured: existing.isConfigured ?? false,
            hasErrors: existing.hasErrors ?? false,
            inputMappings: resolvedInputMappings,
        } as AgentNodeData,
    } as Node<AgentNodeData>
}

export function normalizeGraphSpecForSave(
    nodes: Node<AgentNodeData>[],
    edges: Edge[],
    options: GraphSpecNormalizeOptions = {}
) {
    const normalizedNodes = nodes.map((node) => ({
        ...node,
        input_mappings:
            (node as any).input_mappings ||
            node.data?.config?.input_mappings ||
            (node.data as any)?.inputMappings,
    }))
    const normalizedEdges = edges.map((edge) => ({
        ...edge,
        source_handle: (edge as any).source_handle || (edge as any).sourceHandle,
        target_handle: (edge as any).target_handle || (edge as any).targetHandle,
    }))
    return {
        spec_version: resolveGraphSpecVersion(nodes, options.specVersion),
        nodes: normalizedNodes,
        edges: normalizedEdges,
    }
}

export function normalizeBuilderEdge(edge: Edge): Edge {
    const sourceHandle = (edge as any).sourceHandle ?? (edge as any).source_handle
    const targetHandle = (edge as any).targetHandle ?? (edge as any).target_handle
    return {
        ...edge,
        sourceHandle: sourceHandle ?? undefined,
        targetHandle: targetHandle ?? undefined,
    }
}

export function normalizeBuilderEdges(edges: Edge[]) {
    return edges.map(normalizeBuilderEdge)
}

export function resolveGraphSpecVersion(
    nodes: Node<AgentNodeData>[],
    incomingVersion?: string
): string {
    const hasOrchestrationV2Nodes = nodes.some((node) => {
        const nodeType = (node.type || (node.data as AgentNodeData | undefined)?.nodeType) as AgentNodeType | undefined
        return !!nodeType && ORCHESTRATION_V2_NODE_TYPES.has(nodeType)
    })

    if (hasOrchestrationV2Nodes) {
        return "2.0"
    }

    if (incomingVersion) {
        return incomingVersion
    }

    return "1.0"
}
