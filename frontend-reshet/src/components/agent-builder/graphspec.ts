import { Edge, Node } from "@xyflow/react"

import { AgentNodeData, AgentNodeType, getNodeSpec } from "./types"

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
    edges: Edge[]
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
    return { spec_version: "1.0", nodes: normalizedNodes, edges: normalizedEdges }
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
