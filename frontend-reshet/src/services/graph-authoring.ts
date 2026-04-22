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
  const next = { ...(currentConfig || {}) }
  if (!configSchema || typeof configSchema !== "object") return next
  const properties = configSchema.properties && typeof configSchema.properties === "object"
    ? configSchema.properties as Record<string, Record<string, any>>
    : {}
  Object.entries(properties).forEach(([name, propertySchema]) => {
    if (next[name] !== undefined) return
    if (Object.prototype.hasOwnProperty.call(propertySchema, "default")) {
      next[name] = propertySchema.default
    }
  })
  return next
}
