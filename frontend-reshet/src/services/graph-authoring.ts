export type BuilderEditorKind = "generic" | "start" | "end" | "classify" | "set_state"

export interface BranchingHint {
  kind: string
  field?: string
  id_key?: string
  label_key?: string
  static_handles?: string[]
  default_handles?: string[]
}

export interface GraphHints {
  editor: BuilderEditorKind
  branching?: BranchingHint
}

export interface NodeCatalogItem {
  type: string
  title: string
  description?: string
  category: string
  input_type: string
  output_type: string
  required_config_fields: string[]
  icon?: string
  color?: string
  editor?: BuilderEditorKind
}

export interface NodeAuthoringSpec {
  type: string
  title: string
  description?: string
  category: string
  input_type: string
  output_type: string
  config_schema: Record<string, any>
  output_schema?: Record<string, any> | null
  field_contracts?: Record<string, any> | null
  graph_hints?: GraphHints | null
}

export interface NodeSchemaResponse {
  specs: Record<string, NodeAuthoringSpec>
  unknown: string[]
  instance_contract: Record<string, any>
}

export type FieldWidget =
  | "string"
  | "text"
  | "number"
  | "boolean"
  | "secret"
  | "select"
  | "model"
  | "tool"
  | "tool_list"
  | "agent_select"
  | "knowledge_store_select"
  | "retrieval_pipeline_select"
  | "variable_list"
  | "template_string"
  | "expression"
  | "condition_list"
  | "mapping_list"
  | "assignment_list"
  | "category_list"
  | "field_mapping"
  | "scope_subset"
  | "spawn_targets"
  | "route_table"
  | "value_ref"
  | "json"
  | "file_path"
  | "code"

export interface AuthoringFieldSpec {
  name: string
  label: string
  required: boolean
  description?: string
  default?: unknown
  placeholder?: string
  fieldType: FieldWidget
  options?: Array<{ value: string; label: string }>
  visibility?: "simple" | "advanced" | "both"
  group?: string
  dependsOn?: { field: string; equals?: unknown; notEquals?: unknown }
  helpKind?: string
  prompt_capable?: boolean
  prompt_surface?: string
  artifactInputs?: Array<{ name: string; type: string; required?: boolean; description?: string }>
}

function toLabel(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
}

function inferWidget(name: string, propertySchema: Record<string, any>): FieldWidget {
  const type = propertySchema.type
  if (type === "boolean") return "boolean"
  if (type === "integer" || type === "number") return "number"
  if (propertySchema.enum) return "select"
  if (type === "array") return "json"
  if (type === "object") return "json"
  if (name === "instructions" || name === "prompt") return "text"
  return "string"
}

export function authoringFieldsFromSchema(configSchema?: Record<string, any> | null): AuthoringFieldSpec[] {
  if (!configSchema || typeof configSchema !== "object") return []
  const properties = configSchema.properties && typeof configSchema.properties === "object"
    ? configSchema.properties as Record<string, Record<string, any>>
    : {}
  const required = new Set(Array.isArray(configSchema.required) ? configSchema.required.map(String) : [])
  const order = Array.isArray(configSchema["x-ui"]?.order) ? configSchema["x-ui"].order.map(String) : Object.keys(properties)
  const orderedNames = [...order, ...Object.keys(properties).filter((name) => !order.includes(name))]
  return orderedNames
    .filter((name) => properties[name])
    .map((name) => {
      const propertySchema = properties[name] || {}
      const ui = propertySchema["x-ui"] && typeof propertySchema["x-ui"] === "object"
        ? propertySchema["x-ui"] as Record<string, any>
        : {}
      const options = Array.isArray(propertySchema.enum)
        ? propertySchema.enum.map((value: unknown) => ({ value: String(value), label: String(value) }))
        : undefined
      return {
        name,
        label: String(propertySchema.title || toLabel(name)),
        required: required.has(name),
        description: typeof propertySchema.description === "string" ? propertySchema.description : undefined,
        default: propertySchema.default,
        placeholder: typeof ui.placeholder === "string" ? ui.placeholder : undefined,
        fieldType: (ui.widget || inferWidget(name, propertySchema)) as FieldWidget,
        options,
        visibility: ui.visibility,
        group: ui.group,
        dependsOn: ui.dependsOn,
        helpKind: ui.helpKind,
        prompt_capable: ui.promptCapable,
        prompt_surface: ui.promptSurface,
        artifactInputs: Array.isArray(ui.artifactInputs) ? ui.artifactInputs : undefined,
      }
    })
}

export function schemaRows(configSchema?: Record<string, any> | null): string[][] {
  const rows = configSchema?.["x-ui"]?.rows
  return Array.isArray(rows) ? rows.filter(Array.isArray).map((row) => row.map(String)) : []
}

export function applySchemaDefaults(configSchema?: Record<string, any> | null, currentConfig?: Record<string, unknown>): Record<string, unknown> {
  if (!configSchema || typeof configSchema !== "object") {
    return { ...(currentConfig || {}) }
  }
  const normalized = applyNestedSchemaDefaults(configSchema as Record<string, any>, currentConfig ?? MISSING)
  return normalized && typeof normalized === "object" && !Array.isArray(normalized)
    ? normalized as Record<string, unknown>
    : { ...(currentConfig || {}) }
}

const MISSING = Symbol("missing-schema-default")

function schemaHasDefaults(schema?: Record<string, any> | null): boolean {
  if (!schema || typeof schema !== "object") return false
  if (Object.prototype.hasOwnProperty.call(schema, "default")) return true
  const properties = schema.properties && typeof schema.properties === "object"
    ? schema.properties as Record<string, Record<string, any>>
    : null
  if (properties) {
    return Object.values(properties).some((value) => schemaHasDefaults(value))
  }
  return Boolean(schema.items && typeof schema.items === "object" && schemaHasDefaults(schema.items))
}

function cloneValue<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => cloneValue(item)) as T
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, cloneValue(item)])) as T
  }
  return value
}

function applyNestedSchemaDefaults(schema: Record<string, any>, currentValue: unknown): unknown {
  if (currentValue === MISSING && Object.prototype.hasOwnProperty.call(schema, "default")) {
    return cloneValue(schema.default)
  }

  const properties = schema.properties && typeof schema.properties === "object"
    ? schema.properties as Record<string, Record<string, any>>
    : null
  if (properties || schema.type === "object") {
    const next: Record<string, unknown> = currentValue && typeof currentValue === "object" && !Array.isArray(currentValue)
      ? { ...(currentValue as Record<string, unknown>) }
      : {}
    Object.entries(properties || {}).forEach(([name, propertySchema]) => {
      const hadExistingValue = Object.prototype.hasOwnProperty.call(next, name)
      const normalized = applyNestedSchemaDefaults(propertySchema, hadExistingValue ? next[name] : MISSING)
      if (normalized === MISSING) return
      if (!hadExistingValue && normalized && typeof normalized === "object" && !Array.isArray(normalized) && Object.keys(normalized as Record<string, unknown>).length === 0 && !Object.prototype.hasOwnProperty.call(propertySchema, "default") && !schemaHasDefaults(propertySchema)) {
        return
      }
      next[name] = normalized
    })
    return next
  }

  if (schema.type === "array" && Array.isArray(currentValue) && schema.items && typeof schema.items === "object") {
    return currentValue.map((item) => applyNestedSchemaDefaults(schema.items as Record<string, any>, item))
  }

  return currentValue === MISSING ? MISSING : cloneValue(currentValue)
}
