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
      if (raw.value_ref && typeof raw.value_ref === "object") {
        const valueRef = raw.value_ref as Record<string, unknown>
        normalized.value_ref = {
          namespace: (valueRef.namespace || "state") as ValueRefNamespace,
          key: String(valueRef.key || "").trim(),
          node_id: valueRef.node_id ? String(valueRef.node_id) : undefined,
          expected_type: valueRef.expected_type ? String(valueRef.expected_type) : undefined,
          label: valueRef.label ? String(valueRef.label) : undefined,
        }
      }
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
        const valueRef = binding.value_ref && typeof binding.value_ref === "object"
          ? (binding.value_ref as ValueRef)
          : null
        if (!valueRef) return acc
        acc.push({
          json_pointer: String(binding.json_pointer || "").trim(),
          value_ref: {
            namespace: (valueRef.namespace || "state") as ValueRefNamespace,
            key: String(valueRef.key || "").trim(),
            node_id: valueRef.node_id ? String(valueRef.node_id) : undefined,
            expected_type: valueRef.expected_type ? String(valueRef.expected_type) : undefined,
            label: valueRef.label ? String(valueRef.label) : undefined,
          },
        })
        return acc
      }, [])
    : buildDefaultEndOutputBindings()
  return { output_schema: outputSchema, output_bindings: outputBindings }
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
