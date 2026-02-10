import { Edge, Node } from "@xyflow/react"

import {
    AgentNodeData,
    AgentNodeType,
    getNodeSpec,
    routeTableRowsToOutcomes,
    routeTableRowsToRouterRoutes,
} from "./types"

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

function stableHash(value: string): string {
    let hash = 0
    for (let i = 0; i < value.length; i += 1) {
        hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0
    }
    return Math.abs(hash).toString(36)
}

function normalizeOrchestrationConfig(node: Node<AgentNodeData>): Record<string, unknown> {
    const existing = (node.data?.config || {}) as Record<string, unknown>
    const config: Record<string, unknown> = { ...existing }
    const nodeType = (node.type || node.data?.nodeType) as AgentNodeType | undefined
    if (!nodeType) {
        return config
    }

    if (nodeType === "spawn_run") {
        const explicitKey = typeof config.idempotency_key === "string" ? config.idempotency_key.trim() : ""
        if (!explicitKey) {
            const target = String(config.target_agent_slug || config.target_agent_id || "unknown")
            const scope = JSON.stringify(config.scope_subset || [])
            config.idempotency_key = `${node.id}:${stableHash(`${target}:${scope}`)}`
        }
    }

    if (nodeType === "spawn_group") {
        const explicitPrefix = typeof config.idempotency_key_prefix === "string" ? config.idempotency_key_prefix.trim() : ""
        if (!explicitPrefix) {
            const targetsRaw = Array.isArray(config.targets) ? config.targets : []
            const targetFingerprints = targetsRaw
                .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
                .map((item) => String(item.target_agent_slug || item.target_agent_id || "unknown"))
                .join("|")
            const scope = JSON.stringify(config.scope_subset || [])
            config.idempotency_key_prefix = `${node.id}:${stableHash(`${targetFingerprints}:${scope}`)}`
        }
    }

    if (nodeType === "router" && Array.isArray(config.route_table)) {
        config.routes = routeTableRowsToRouterRoutes(config.route_table)
    }

    if (nodeType === "judge") {
        if (Array.isArray(config.route_table)) {
            const outcomes = routeTableRowsToOutcomes(config.route_table)
            if (outcomes.length > 0) {
                config.outcomes = outcomes
            }
        }
        if (!Array.isArray(config.outcomes) || config.outcomes.length === 0) {
            const pass = typeof config.pass_outcome === "string" && config.pass_outcome.trim()
                ? config.pass_outcome.trim()
                : "pass"
            const fail = typeof config.fail_outcome === "string" && config.fail_outcome.trim()
                ? config.fail_outcome.trim()
                : "fail"
            config.outcomes = [pass, fail]
        }
    }

    return config
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
        data: node.data
            ? {
                ...node.data,
                config: normalizeOrchestrationConfig(node),
            }
            : node.data,
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
