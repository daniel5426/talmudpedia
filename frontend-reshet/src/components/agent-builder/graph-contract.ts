import type {
  AgentGraphAnalysis,
  AgentGraphInventoryItem,
  AgentGraphNodeOutputGroup,
} from "@/services/agent"

export type ValueRefNamespace = "workflow_input" | "state" | "node_output"

export interface ValueRef {
  namespace: ValueRefNamespace
  key: string
  node_id?: string
  expected_type?: string
  label?: string
}

export interface EndOutputBinding {
  json_pointer: string
  value_ref: ValueRef
}

export interface EndOutputSchemaConfig {
  name?: string
  mode: "simple" | "advanced"
  schema: Record<string, unknown>
}

export interface StateVariableDefinition {
  key: string
  type: "string" | "number" | "boolean" | "object" | "list"
  description?: string
  schema?: Record<string, unknown>
  default_value?: unknown
}

export interface StructuredPropertyDefinition {
  id: string
  key: string
  type: "string" | "number" | "boolean" | "object" | "list"
  description?: string
  value_ref?: ValueRef | null
  children?: StructuredPropertyDefinition[]
}

export interface BranchDefinition {
  id?: string
  name?: string
}

export interface SetStateAssignment {
  key: string
  type?: "string" | "number" | "boolean" | "object" | "list"
  value?: unknown
  value_ref?: ValueRef
}

export interface GraphValueRefConsumer {
  node_id: string
  node_label: string
  location: string
  label: string
}

export function normalizeValueRef(value: unknown): ValueRef | undefined {
  if (!value || typeof value !== "object") return undefined
  const raw = value as Record<string, unknown>
  const key = String(raw.key || "").trim()
  if (!key) return undefined
  const namespace = String(raw.namespace || "state").trim() as ValueRefNamespace
  return {
    namespace,
    key,
    node_id: raw.node_id ? String(raw.node_id).trim() || undefined : undefined,
    expected_type: raw.expected_type ? String(raw.expected_type).trim() || undefined : undefined,
    label: raw.label ? String(raw.label).trim() || undefined : undefined,
  }
}

export function buildDefaultEndOutputSchema(): EndOutputSchemaConfig {
  return {
    name: "workflow_result",
    mode: "simple",
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        response: { type: "string" },
      },
      required: ["response"],
    },
  }
}

export function buildDefaultEndOutputBindings(): EndOutputBinding[] {
  return [
    {
      json_pointer: "/response",
      value_ref: {
        namespace: "workflow_input",
        key: "text",
        label: "Workflow input / text",
      },
    },
  ]
}

export function normalizeStateVariables(value: unknown): StateVariableDefinition[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const raw = item as Record<string, unknown>
      const key = String(raw.key || raw.name || "").trim()
      const type = String(raw.type || "string").trim().toLowerCase()
      if (!key) return null
      const normalized: StateVariableDefinition = {
        key,
        type: (type === "array" ? "list" : type) as StateVariableDefinition["type"],
      }
      if ("description" in raw && typeof raw.description === "string") normalized.description = raw.description
      if ("schema" in raw && raw.schema && typeof raw.schema === "object") normalized.schema = raw.schema as Record<string, unknown>
      if ("default_value" in raw) normalized.default_value = raw.default_value
      else if ("default" in raw) normalized.default_value = raw.default
      return normalized
    })
    .filter((item): item is StateVariableDefinition => !!item)
}

export function normalizeSetStateAssignments(value: unknown): SetStateAssignment[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const raw = item as Record<string, unknown>
      const key = String(raw.key || raw.variable || "").trim()
      if (!key) return null
      const normalized: SetStateAssignment = { key }
      const type = String(raw.type || raw.value_type || "").trim().toLowerCase()
      if (type) {
        normalized.type = (type === "array" ? "list" : type) as SetStateAssignment["type"]
      }
      if ("value" in raw) normalized.value = raw.value
      normalized.value_ref = normalizeValueRef(raw.value_ref)
      return normalized
    })
    .filter((item): item is SetStateAssignment => !!item)
}

export function normalizeEndConfig(value: unknown): { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] } {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {}
  const outputSchema = raw.output_schema && typeof raw.output_schema === "object"
    ? {
        name: String((raw.output_schema as Record<string, unknown>).name || "workflow_result"),
        mode: String((raw.output_schema as Record<string, unknown>).mode || "simple") as EndOutputSchemaConfig["mode"],
        schema: ((raw.output_schema as Record<string, unknown>).schema as Record<string, unknown>) || buildDefaultEndOutputSchema().schema,
      }
    : buildDefaultEndOutputSchema()
  const outputBindings = Array.isArray(raw.output_bindings)
    ? raw.output_bindings.reduce<EndOutputBinding[]>((acc, item) => {
        if (!item || typeof item !== "object") return acc
        const binding = item as Record<string, unknown>
        const valueRef = normalizeValueRef(binding.value_ref)
        if (!valueRef) return acc
        acc.push({
          json_pointer: String(binding.json_pointer || "").trim(),
          value_ref: valueRef,
        })
        return acc
      }, [])
    : buildDefaultEndOutputBindings()
  return { output_schema: outputSchema, output_bindings: outputBindings }
}

function normalizeBranchId(raw: unknown): string {
  return String(raw || "").trim()
}

const OPAQUE_BRANCH_ID_PREFIX = "branch_"

function stableBranchHash(value: string): string {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0
  }
  return Math.abs(hash).toString(36)
}

function isOpaqueBranchId(value: string): boolean {
  return value.startsWith(OPAQUE_BRANCH_ID_PREFIX) && value.length > OPAQUE_BRANCH_ID_PREFIX.length
}

function makeOpaqueBranchId(seed: string, used: Set<string>): string {
  let attempt = 0
  while (true) {
    const hash = stableBranchHash(attempt === 0 ? seed : `${seed}:${attempt}`)
    const candidate = `${OPAQUE_BRANCH_ID_PREFIX}${hash}`
    if (!used.has(candidate)) {
      used.add(candidate)
      return candidate
    }
    attempt += 1
  }
}

type BranchNormalizationResult<T> = {
  items: T[]
}

function deriveStableBranchIds<T extends BranchDefinition>(
  items: T[],
  fallbackPrefix: string,
): BranchNormalizationResult<T> {
  const usedOpaqueIds = new Set<string>()
  const normalizedItems = items.map((item, index) => {
    const explicitId = normalizeBranchId(item.id)
    const rawName = String(item.name || "").trim()
    let nextId = explicitId
    if (!isOpaqueBranchId(nextId)) {
      nextId = makeOpaqueBranchId(`${fallbackPrefix}:${rawName}:${index}`, usedOpaqueIds)
    } else if (usedOpaqueIds.has(nextId)) {
      nextId = makeOpaqueBranchId(`${fallbackPrefix}:${rawName}:${index}`, usedOpaqueIds)
    } else {
      usedOpaqueIds.add(nextId)
    }
    return { ...item, id: nextId }
  })
  return { items: normalizedItems }
}

export function normalizeClassifyCategoriesWithHandleMap(value: unknown): BranchNormalizationResult<Record<string, unknown>> {
  if (!Array.isArray(value)) return { items: [] }
  const normalized = value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const raw = item as Record<string, unknown>
      return {
        ...raw,
        name: String(raw.name || ""),
        description: typeof raw.description === "string" ? raw.description : "",
      }
    })
    .filter((item): item is Record<string, unknown> => !!item)
  return deriveStableBranchIds(normalized, "category")
}

export function normalizeClassifyCategories(value: unknown): Array<Record<string, unknown>> {
  return normalizeClassifyCategoriesWithHandleMap(value).items
}

export function normalizeIfElseConditionsWithHandleMap(value: unknown): BranchNormalizationResult<Record<string, unknown>> {
  if (!Array.isArray(value)) return { items: [] }
  const normalized = value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const raw = item as Record<string, unknown>
      return {
        ...raw,
        name: String(raw.name || ""),
        expression: typeof raw.expression === "string" ? raw.expression : "",
      }
    })
    .filter((item): item is Record<string, unknown> => !!item)
  return deriveStableBranchIds(normalized, "condition")
}

export function normalizeIfElseConditions(value: unknown): Array<Record<string, unknown>> {
  return normalizeIfElseConditionsWithHandleMap(value).items
}

export function normalizeNodeContractConfig(nodeType: string, value: unknown): Record<string, unknown> {
  const config = value && typeof value === "object" ? { ...(value as Record<string, unknown>) } : {}

  if (nodeType === "start") {
    config.state_variables = normalizeStateVariables(config.state_variables)
  }

  if (nodeType === "set_state") {
    config.assignments = normalizeSetStateAssignments(config.assignments)
  }

  if (nodeType === "if_else") {
    config.conditions = normalizeIfElseConditions(config.conditions)
  }

  if (nodeType === "classify") {
    config.categories = normalizeClassifyCategories(config.categories)
  }

  if (nodeType === "classify" && config.input_source && typeof config.input_source === "object") {
    const normalized = normalizeValueRef(config.input_source)
    if (normalized) {
      config.input_source = normalized
    }
  }

  if (nodeType === "end") {
    const normalized = normalizeEndConfig(config)
    config.output_schema = normalized.output_schema
    config.output_bindings = normalized.output_bindings
  }

  return config
}

export interface ValueRefOption extends AgentGraphInventoryItem {
  value_ref: ValueRef
}

export function getValueRefGroups(
  analysis?: AgentGraphAnalysis | null,
  nodeId?: string | null,
): Array<{ label: string; options: ValueRefOption[] }> {
  if (!analysis) return []

  const workflowInput = (analysis.inventory.workflow_input || []).map((item) => ({
    ...item,
    value_ref: {
      namespace: "workflow_input" as const,
      key: item.key,
      expected_type: item.type,
      label: item.label,
    },
  }))
  const state = (analysis.inventory.state || []).map((item) => ({
    ...item,
    value_ref: {
      namespace: "state" as const,
      key: item.key,
      expected_type: item.type,
      label: item.label,
    },
  }))
  const scopedNodeOutputs = nodeId
    ? analysis.inventory.accessible_node_outputs_by_node?.[nodeId] || []
    : []
  const nodeOutputGroups = scopedNodeOutputs.map((group: AgentGraphNodeOutputGroup) => ({
    label: group.node_label || group.node_id,
    options: (group.fields || []).map((item) => ({
      ...item,
      namespace: "node_output" as const,
      node_id: group.node_id,
      label: `${group.node_label} / ${item.label || item.key}`,
      value_ref: {
        namespace: "node_output" as const,
        node_id: group.node_id,
        key: item.key,
        expected_type: item.type,
        label: `${group.node_label} / ${item.label || item.key}`,
      },
    })),
  }))

  return [
    { label: "Workflow Input", options: workflowInput },
    { label: "State", options: state },
    ...nodeOutputGroups.filter((group) => group.options.length > 0).map((group) => ({
      label: `Node Output: ${group.label}`,
      options: group.options,
    })),
  ].filter((group) => group.options.length > 0)
}

export function isValueRefTypeCompatible(optionType: string, expectedTypes?: string[]) {
  if (!expectedTypes || expectedTypes.length === 0) return true
  if (!optionType || optionType === "unknown") return true
  return expectedTypes.includes(optionType) || expectedTypes.includes("unknown")
}

export function isValueRefSemanticTypeCompatible(optionSemanticType?: string | null, expectedSemanticTypes?: string[]) {
  if (!expectedSemanticTypes || expectedSemanticTypes.length === 0) return true
  if (!optionSemanticType) return false
  return expectedSemanticTypes.includes(optionSemanticType)
}

function normalizeStructuredPropertyType(raw: unknown): StructuredPropertyDefinition["type"] {
  const normalized = String(raw || "string").trim().toLowerCase()
  if (normalized === "array") return "list"
  if (normalized === "number" || normalized === "boolean" || normalized === "object" || normalized === "list") return normalized
  return "string"
}

function createStructuredPropertyId() {
  return `prop_${Math.random().toString(36).slice(2, 10)}`
}

export function createStructuredProperty(
  patch: Partial<StructuredPropertyDefinition> = {},
): StructuredPropertyDefinition {
  return {
    id: patch.id || createStructuredPropertyId(),
    key: patch.key || "",
    type: normalizeStructuredPropertyType(patch.type),
    description: patch.description,
    value_ref: patch.value_ref ?? null,
    children: Array.isArray(patch.children) ? patch.children : undefined,
  }
}

function normalizeStructuredChildren(raw: unknown): StructuredPropertyDefinition[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => normalizeStructuredProperty(item))
    .filter((item): item is StructuredPropertyDefinition => !!item)
}

export function normalizeStructuredProperty(raw: unknown): StructuredPropertyDefinition | null {
  if (!raw || typeof raw !== "object") return null
  const value = raw as Record<string, unknown>
  const type = normalizeStructuredPropertyType(value.type)
  return {
    id: typeof value.id === "string" && value.id.trim() ? value.id : createStructuredPropertyId(),
    key: String(value.key || value.name || "").trim(),
    type,
    description: typeof value.description === "string" ? value.description : undefined,
    value_ref: normalizeValueRef(value.value_ref),
    children: type === "object" ? normalizeStructuredChildren(value.children) : [],
  }
}

export function normalizeStructuredProperties(raw: unknown): StructuredPropertyDefinition[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => normalizeStructuredProperty(item))
    .filter((item): item is StructuredPropertyDefinition => !!item)
}

type ValueRefPathSegment = string | number

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

function collectMatchingValueRefPaths(
  value: unknown,
  target: Pick<ValueRef, "namespace" | "key">,
  path: ValueRefPathSegment[] = [],
): ValueRefPathSegment[][] {
  const normalized = normalizeValueRef(value)
  if (normalized && normalized.namespace === target.namespace && normalized.key === target.key) {
    return [path]
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectMatchingValueRefPaths(item, target, [...path, index]))
  }
  if (!isRecord(value)) return []
  return Object.entries(value).flatMap(([key, child]) => collectMatchingValueRefPaths(child, target, [...path, key]))
}

function describeValueRefConsumerLocation(
  nodeType: string,
  config: Record<string, unknown>,
  path: ValueRefPathSegment[],
): string {
  if (nodeType === "end" && path[0] === "output_bindings" && typeof path[1] === "number") {
    const binding = normalizeEndConfig(config).output_bindings[path[1]]
    return binding?.json_pointer || `output binding ${path[1] + 1}`
  }
  if (nodeType === "set_state" && path[0] === "assignments" && typeof path[1] === "number") {
    const assignment = normalizeSetStateAssignments(config.assignments)[path[1]]
    return assignment?.key ? `state:${assignment.key}` : `assignment ${path[1] + 1}`
  }
  return path
    .map((segment) => (typeof segment === "number" ? `[${segment + 1}]` : segment))
    .join(".")
}

function getNodeType(rawNode: unknown): string {
  if (!isRecord(rawNode)) return ""
  if (typeof rawNode.type === "string" && rawNode.type.trim()) return rawNode.type
  if (isRecord(rawNode.data) && typeof rawNode.data.nodeType === "string") return rawNode.data.nodeType
  return ""
}

function getNodeLabel(rawNode: unknown, nodeType: string): string {
  if (!isRecord(rawNode)) return nodeType || "Node"
  if (isRecord(rawNode.data)) {
    if (typeof rawNode.data.displayName === "string" && rawNode.data.displayName.trim()) return rawNode.data.displayName
    if (typeof rawNode.data.label === "string" && rawNode.data.label.trim()) return rawNode.data.label
  }
  if (typeof rawNode.id === "string" && rawNode.id.trim()) return rawNode.id
  return nodeType || "Node"
}

function getNodeConfig(rawNode: unknown): Record<string, unknown> {
  if (!isRecord(rawNode)) return {}
  if (isRecord(rawNode.config)) return rawNode.config
  if (isRecord(rawNode.data) && isRecord(rawNode.data.config)) return rawNode.data.config
  return {}
}

export function getGraphValueRefConsumers(
  graphDefinition: { nodes?: unknown[] } | undefined,
  target: Pick<ValueRef, "namespace" | "key">,
): GraphValueRefConsumer[] {
  const nodes = Array.isArray(graphDefinition?.nodes) ? graphDefinition.nodes : []
  return nodes.flatMap((node) => {
    const nodeType = getNodeType(node)
    if (!nodeType) return []
    const config = normalizeNodeContractConfig(nodeType, getNodeConfig(node))
    const paths = collectMatchingValueRefPaths(config, target)
    if (paths.length === 0) return []
    const nodeId = isRecord(node) && typeof node.id === "string" ? node.id : nodeType
    const nodeLabel = getNodeLabel(node, nodeType)
    return paths.map((path) => {
      const location = describeValueRefConsumerLocation(nodeType, config, path)
      return {
        node_id: nodeId,
        node_label: nodeLabel,
        location,
        label: `${nodeLabel} -> ${location}`,
      }
    })
  })
}

function getSchemaType(raw: unknown): StructuredPropertyDefinition["type"] {
  if (!raw || typeof raw !== "object") return "string"
  const schema = raw as Record<string, unknown>
  const type = normalizeStructuredPropertyType(schema.type)
  return type
}

function schemaToStructuredChildren(
  schema: Record<string, unknown>,
  bindings: EndOutputBinding[],
  pointerPrefix: string,
): StructuredPropertyDefinition[] {
  const properties = schema.properties && typeof schema.properties === "object"
    ? schema.properties as Record<string, Record<string, unknown>>
    : {}
  return Object.entries(properties).map(([key, propertySchema]) => {
    const pointer = `${pointerPrefix}/${key}`
    const type = getSchemaType(propertySchema)
    const node = createStructuredProperty({
      key,
      type,
      description: typeof propertySchema?.description === "string" ? propertySchema.description : undefined,
      value_ref: bindings.find((binding) => binding.json_pointer === pointer)?.value_ref || null,
    })
    if (type === "object") {
      node.children = schemaToStructuredChildren(propertySchema, bindings, pointer)
    }
    return node
  })
}

export function endSchemaToStructuredProperties(
  schema: Record<string, unknown>,
  bindings: EndOutputBinding[],
): StructuredPropertyDefinition[] {
  return schemaToStructuredChildren(schema, bindings, "")
}

function structuredPropertyToSchema(node: StructuredPropertyDefinition): Record<string, unknown> {
  if (node.type === "object") {
    const children = Array.isArray(node.children) ? node.children.filter((item) => item.key.trim()) : []
    return {
      type: "object",
      ...(node.description ? { description: node.description } : {}),
      additionalProperties: false,
      properties: Object.fromEntries(children.map((child) => [child.key.trim(), structuredPropertyToSchema(child)])),
      required: children.map((child) => child.key.trim()),
    }
  }
  return {
    type: node.type === "list" ? "array" : node.type,
    ...(node.description ? { description: node.description } : {}),
  }
}

function collectStructuredBindings(
  nodes: StructuredPropertyDefinition[],
  pointerPrefix = "",
): EndOutputBinding[] {
  return nodes.flatMap((node) => {
    const key = node.key.trim()
    if (!key) return []
    const pointer = `${pointerPrefix}/${key}`
    const own = node.value_ref ? [{ json_pointer: pointer, value_ref: node.value_ref }] : []
    if (node.type !== "object") return own
    return [...own, ...collectStructuredBindings(node.children || [], pointer)]
  })
}

export function structuredPropertiesToEndConfig(
  nodes: StructuredPropertyDefinition[],
  schemaName?: string,
): { output_schema: EndOutputSchemaConfig; output_bindings: EndOutputBinding[] } {
  const filtered = nodes.filter((node) => node.key.trim())
  return {
    output_schema: {
      name: schemaName || "workflow_result",
      mode: "simple",
      schema: {
        type: "object",
        additionalProperties: false,
        properties: Object.fromEntries(filtered.map((node) => [node.key.trim(), structuredPropertyToSchema(node)])),
        required: filtered.map((node) => node.key.trim()),
      },
    },
    output_bindings: collectStructuredBindings(filtered),
  }
}

export function stateVariableObjectSchemaToStructuredProperties(
  schema?: Record<string, unknown>,
): StructuredPropertyDefinition[] {
  if (!schema || typeof schema !== "object") return []
  return schemaToStructuredChildren(schema, [], "")
}

export function structuredPropertiesToObjectSchema(nodes: StructuredPropertyDefinition[]): Record<string, unknown> {
  const filtered = nodes.filter((node) => node.key.trim())
  return {
    type: "object",
    additionalProperties: false,
    properties: Object.fromEntries(filtered.map((node) => [node.key.trim(), structuredPropertyToSchema(node)])),
    required: filtered.map((node) => node.key.trim()),
  }
}
