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
  default_value?: unknown
}

export interface SetStateAssignment {
  key: string
  type?: "string" | "number" | "boolean" | "object" | "list"
  value?: unknown
  value_ref?: ValueRef
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
        key: "input_as_text",
        label: "Workflow input / input_as_text",
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

export function normalizeNodeContractConfig(nodeType: string, value: unknown): Record<string, unknown> {
  const config = value && typeof value === "object" ? { ...(value as Record<string, unknown>) } : {}

  if (nodeType === "start") {
    config.state_variables = normalizeStateVariables(config.state_variables)
  }

  if (nodeType === "set_state") {
    config.assignments = normalizeSetStateAssignments(config.assignments)
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

export function getValueRefGroups(analysis?: AgentGraphAnalysis | null): Array<{ label: string; options: ValueRefOption[] }> {
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
  const nodeOutputGroups = (analysis.inventory.node_outputs || []).map((group: AgentGraphNodeOutputGroup) => ({
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
