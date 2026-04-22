import { Edge, Node } from "@xyflow/react"

import {
    AgentNodeData,
    AgentNodeType,
    getNodeUiDefaults,
    routeTableRowsToOutcomes,
    routeTableRowsToRouterRoutes,
} from "./types"
import {
    normalizeClassifyCategoriesWithHandleMap,
    normalizeIfElseConditionsWithHandleMap,
    normalizeNodeContractConfig,
    type StateVariableDefinition,
} from "./graph-contract"
import type { AgentGraphDefinition } from "@/services/agent"

interface GraphSpecNormalizeOptions {
    specVersion?: string
    workflowContract?: AgentGraphDefinition["workflow_contract"]
    stateContract?: AgentGraphDefinition["state_contract"]
}

type BuilderNode = Node<AgentNodeData> & {
    config?: Record<string, unknown>
    nodeType?: AgentNodeType
    input_mappings?: Record<string, string>
}

const DEFAULT_WORKFLOW_CONTRACT: NonNullable<AgentGraphDefinition["workflow_contract"]> = {
    inputs: [
        {
            key: "text",
            type: "string",
            enabled: true,
            required: false,
            label: "Text",
            description: "Primary text input for the workflow",
            semantic_type: "text",
            readonly: true,
            derived: false,
        },
        {
            key: "files",
            type: "list",
            enabled: true,
            required: false,
            label: "Files",
            description: "General uploaded files for the workflow",
            semantic_type: "files",
            readonly: true,
            derived: false,
        },
        {
            key: "audio",
            type: "list",
            enabled: true,
            required: false,
            label: "Audio",
            description: "Audio attachments for speech or sound workflows",
            semantic_type: "audio",
            readonly: true,
            derived: false,
        },
        {
            key: "images",
            type: "list",
            enabled: true,
            required: false,
            label: "Images",
            description: "Image attachments for vision-aware workflows",
            semantic_type: "images",
            readonly: true,
            derived: false,
        },
    ],
}

function normalizeStateContractVariables(value: unknown): StateVariableDefinition[] {
    if (!Array.isArray(value)) return []
    return value
        .map((item) => normalizeNodeContractConfig("start", { state_variables: [item] }).state_variables)
        .flat()
        .filter((item): item is StateVariableDefinition => !!item && typeof item === "object")
}

function normalizeWorkflowContract(value: AgentGraphDefinition["workflow_contract"] | undefined): NonNullable<AgentGraphDefinition["workflow_contract"]> {
    const inputs = Array.isArray(value?.inputs) ? value.inputs : []
    const deduped = new Map<string, NonNullable<AgentGraphDefinition["workflow_contract"]>["inputs"][number]>()
    const defaultsByKey = new Map(DEFAULT_WORKFLOW_CONTRACT.inputs.map((item) => [item.key, item]))
    const legacyKeyMap: Record<string, string> = {
        input_as_text: "text",
        attachments: "files",
        audio_attachments: "audio",
        primary_audio_attachment: "audio",
    }
    for (const raw of inputs) {
        const rawKey = String(raw?.key || "").trim()
        const key = legacyKeyMap[rawKey] || rawKey
        if (!key || deduped.has(key)) continue
        const defaults = defaultsByKey.get(key)
        deduped.set(key, {
            ...(defaults ? { ...defaults } : { key, type: "unknown" }),
            enabled: raw?.enabled !== false,
            required: Boolean(raw?.required),
        })
    }
    for (const item of DEFAULT_WORKFLOW_CONTRACT.inputs) {
        if (!deduped.has(item.key)) {
            deduped.set(item.key, { ...item })
        }
    }
    return { inputs: Array.from(deduped.values()) }
}

function normalizeStateContract(value: AgentGraphDefinition["state_contract"] | undefined, nodes?: Node<AgentNodeData>[]): NonNullable<AgentGraphDefinition["state_contract"]> {
    const explicitVariables = normalizeStateContractVariables(value?.variables)
    if (explicitVariables.length > 0) {
        return { variables: explicitVariables }
    }
    const startNode = (nodes || []).find((node) => (node.type || node.data?.nodeType) === "start")
    const startConfig = (((startNode as unknown as { config?: Record<string, unknown> } | undefined)?.config) || startNode?.data?.config || {}) as Record<string, unknown>
    return {
        variables: normalizeStateContractVariables(startConfig.state_variables),
    }
}

export function normalizeGraphDefinition(raw?: Partial<AgentGraphDefinition> | null): AgentGraphDefinition {
    const rawNodes = (Array.isArray(raw?.nodes) ? raw.nodes : []) as Node<AgentNodeData>[]
    const normalizedStateContract = normalizeStateContract(raw?.state_contract, rawNodes)
    const normalizedNodes = rawNodes.map((node) => {
        if (!node || typeof node !== "object") return node as any
        const payload = normalizeBranchAwareNode(node as Node)
        if ((payload.type || payload.data?.nodeType) === "start") {
            return {
                ...payload,
                config: {},
                data: {
                    ...payload.data,
                    config: {},
                },
            }
        }
        return payload
    })
    const normalizedEdges = normalizeBuilderEdges(Array.isArray(raw?.edges) ? raw.edges : [])
    return {
        spec_version: "4.0",
        workflow_contract: normalizeWorkflowContract(raw?.workflow_contract),
        state_contract: normalizedStateContract,
        nodes: normalizedNodes,
        edges: normalizedEdges,
    }
}

function stableHash(value: string): string {
    let hash = 0
    for (let i = 0; i < value.length; i += 1) {
        hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0
    }
    return Math.abs(hash).toString(36)
}

function normalizeOrchestrationConfig(node: Node<AgentNodeData>): Record<string, unknown> {
    const existing = (((node as unknown as { config?: Record<string, unknown> }).config) || {}) as Record<string, unknown>
    const config: Record<string, unknown> = { ...existing }
    const nodeType = (node.type || node.data?.nodeType) as AgentNodeType | undefined
    if (!nodeType) {
        return config
    }

    if (nodeType === "spawn_run") {
        const explicitKey = typeof config.idempotency_key === "string" ? config.idempotency_key.trim() : ""
        if (!explicitKey) {
            const target = String(config.target_agent_id || "unknown")
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
                .map((item) => String(item.target_agent_id || "unknown"))
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

function normalizeBranchAwareNode(node: Node | BuilderNode): Node<AgentNodeData> {
    const raw = node as BuilderNode
    const existing = (raw.data || {}) as Partial<AgentNodeData>
    const nodeType = (raw.type || raw.nodeType || existing.nodeType || "transform") as AgentNodeType
    const rawConfig = raw.config ?? {}
    if (nodeType === "classify") {
        const result = normalizeClassifyCategoriesWithHandleMap((rawConfig as Record<string, unknown>).categories)
        ;(rawConfig as Record<string, unknown>).categories = result.items
    } else if (nodeType === "if_else") {
        const result = normalizeIfElseConditionsWithHandleMap((rawConfig as Record<string, unknown>).conditions)
        ;(rawConfig as Record<string, unknown>).conditions = result.items
    }
    return normalizeBuilderNode({ ...raw, config: rawConfig })
}

export function normalizeBuilderNode(node: Node | BuilderNode): Node<AgentNodeData> {
    const raw = node as BuilderNode
    const existing = (raw.data || {}) as Partial<AgentNodeData>
    const nodeType = (raw.type || raw.nodeType || existing.nodeType || "transform") as AgentNodeType
    const defaults = getNodeUiDefaults(nodeType)
    const rawConfig = raw.config ?? {}
    const config = normalizeNodeContractConfig(nodeType, rawConfig)
    const resolvedInputMappings = existing.inputMappings ?? raw.input_mappings
    if (resolvedInputMappings && !("input_mappings" in config)) {
        config["input_mappings"] = resolvedInputMappings
    }
    const category =
        existing.category ??
        defaults?.category ??
        (typeof nodeType === "string" && nodeType.startsWith("artifact:") ? "action" : "data")
    const displayName =
        existing.displayName ??
        defaults?.displayName ??
        (config?.label as string) ??
        nodeType
    const inputType = existing.inputType ?? defaults?.inputType ?? "any"
    const outputType = existing.outputType ?? defaults?.outputType ?? "any"

    const normalizedNode: BuilderNode = {
        ...node,
        type: nodeType,
        config,
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
    }

    return normalizedNode as unknown as Node<AgentNodeData>
}

export function normalizeGraphSpecForSave(
    nodes: Node<AgentNodeData>[],
    edges: Edge[],
    options: GraphSpecNormalizeOptions = {}
) {
    const normalizedNodes = nodes.map((node) => {
        const branchAwareNode = normalizeBranchAwareNode(node)
        const orchestrationConfig = normalizeOrchestrationConfig(branchAwareNode)
        const nodeType = ((branchAwareNode.type || branchAwareNode.data?.nodeType || "transform") as AgentNodeType)
        const normalizedConfig = normalizeNodeContractConfig(nodeType, orchestrationConfig)
        const rawData = branchAwareNode.data ? { ...branchAwareNode.data } : undefined
        if (rawData) {
            delete (rawData as Record<string, unknown>).config
            delete (rawData as Record<string, unknown>).inputMappings
        }
        return {
            ...branchAwareNode,
            config: normalizedConfig,
            data: rawData,
            input_mappings:
                (branchAwareNode as any).input_mappings ||
                normalizedConfig.input_mappings ||
                (branchAwareNode.data as any)?.inputMappings,
        }
    })
    const normalizedEdges = edges.map((edge) => ({
        ...edge,
        source_handle: (edge as any).source_handle || (edge as any).sourceHandle,
        target_handle: (edge as any).target_handle || (edge as any).targetHandle,
    }))
    return {
        spec_version: resolveGraphSpecVersion(nodes, options.specVersion),
        workflow_contract: normalizeWorkflowContract(options.workflowContract),
        state_contract: normalizeStateContract(options.stateContract, nodes),
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
    void nodes
    void incomingVersion
    return "4.0"
}
