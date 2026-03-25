import type { AgentArtifactContract, ArtifactKind, RAGArtifactContract, ToolArtifactContract } from "@/services/artifacts";

type JsonSchema = Record<string, unknown>;

export function resolveArtifactInputSchema(
  kind: ArtifactKind,
  contracts: {
    agentContract?: AgentArtifactContract | null;
    ragContract?: RAGArtifactContract | null;
    toolContract?: ToolArtifactContract | null;
  },
): JsonSchema {
  if (kind === "agent_node") return unwrapContractInputSchema(contracts.agentContract, "agent_contract");
  if (kind === "rag_operator") return unwrapContractInputSchema(contracts.ragContract, "rag_contract");
  return unwrapContractInputSchema(contracts.toolContract, "tool_contract");
}

export function buildArtifactTestInputJson(schema: JsonSchema): string {
  return JSON.stringify(buildExampleFromSchema(schema), null, 2);
}

export function validateArtifactTestInput(value: unknown, schema: JsonSchema): string[] {
  if (!hasMeaningfulSchema(schema)) return [];
  return validateAgainstSchema(value, schema, "$");
}

function normalizeSchemaObject(value: unknown): JsonSchema {
  return value && typeof value === "object" ? ({ ...(value as JsonSchema) }) : {};
}

function unwrapContractInputSchema(value: unknown, wrapperKey: "agent_contract" | "rag_contract" | "tool_contract"): JsonSchema {
  const direct = normalizeSchemaObject(value);
  if (isRecord(direct.input_schema)) return normalizeSchemaObject(direct.input_schema);
  const wrapped = normalizeSchemaObject(direct[wrapperKey]);
  if (isRecord(wrapped.input_schema)) return normalizeSchemaObject(wrapped.input_schema);
  return {};
}

function hasMeaningfulSchema(schema: JsonSchema): boolean {
  return Object.keys(schema).length > 0;
}

function buildExampleFromSchema(schema: JsonSchema): unknown {
  const normalized = normalizeVariantSchema(schema);
  if ("default" in normalized) return normalized.default;
  if ("example" in normalized) return normalized.example;
  if (Array.isArray(normalized.examples) && normalized.examples.length > 0) return normalized.examples[0];
  if (Array.isArray(normalized.enum) && normalized.enum.length > 0) return normalized.enum[0];

  const type = typeof normalized.type === "string" ? normalized.type : undefined;
  if (type === "object" || normalized.properties || normalized.required) {
    const properties = isRecord(normalized.properties) ? normalized.properties : {};
    const required = Array.isArray(normalized.required) ? normalized.required.filter((item): item is string => typeof item === "string") : [];
    const keys = required.length > 0 ? required : Object.keys(properties);
    const result: Record<string, unknown> = {};
    for (const key of keys) {
      result[key] = buildExampleFromSchema(normalizeSchemaObject(properties[key]));
    }
    return result;
  }
  if (type === "array" || normalized.items) {
    const itemSchema = normalizeSchemaObject(normalized.items);
    const minItems = typeof normalized.minItems === "number" && normalized.minItems > 0 ? normalized.minItems : 1;
    return Array.from({ length: minItems }, () => buildExampleFromSchema(itemSchema));
  }
  if (type === "string") return "";
  if (type === "integer" || type === "number") {
    if (typeof normalized.minimum === "number") return normalized.minimum;
    return 0;
  }
  if (type === "boolean") return false;
  if (type === "null") return null;
  return {};
}

function validateAgainstSchema(value: unknown, schema: JsonSchema, path: string): string[] {
  const normalized = normalizeVariantSchema(schema);
  const inferredType = typeof normalized.type === "string" ? normalized.type : inferSchemaType(normalized);
  const errors: string[] = [];

  if (Array.isArray(normalized.enum) && normalized.enum.length > 0) {
    const allowed = normalized.enum;
    if (!allowed.some((candidate) => Object.is(candidate, value))) {
      errors.push(`${path} must be one of ${allowed.map((item) => JSON.stringify(item)).join(", ")}.`);
      return errors;
    }
  }

  if (!inferredType) return errors;

  if (inferredType === "object") {
    if (!isRecord(value) || Array.isArray(value)) {
      return [`${path} must be an object.`];
    }
    const properties = isRecord(normalized.properties) ? normalized.properties : {};
    const required = Array.isArray(normalized.required) ? normalized.required.filter((item): item is string => typeof item === "string") : [];
    for (const key of required) {
      if (!(key in value)) errors.push(`${joinPath(path, key)} is required.`);
    }
    for (const [key, propertyValue] of Object.entries(value)) {
      if (key in properties) {
        errors.push(...validateAgainstSchema(propertyValue, normalizeSchemaObject(properties[key]), joinPath(path, key)));
        continue;
      }
      if (normalized.additionalProperties === false) {
        errors.push(`${joinPath(path, key)} is not allowed.`);
      } else if (isRecord(normalized.additionalProperties)) {
        errors.push(
          ...validateAgainstSchema(
            propertyValue,
            normalizeSchemaObject(normalized.additionalProperties),
            joinPath(path, key),
          ),
        );
      }
    }
    return errors;
  }

  if (inferredType === "array") {
    if (!Array.isArray(value)) return [`${path} must be an array.`];
    if (typeof normalized.minItems === "number" && value.length < normalized.minItems) {
      errors.push(`${path} must contain at least ${normalized.minItems} item${normalized.minItems === 1 ? "" : "s"}.`);
    }
    if (typeof normalized.maxItems === "number" && value.length > normalized.maxItems) {
      errors.push(`${path} must contain at most ${normalized.maxItems} item${normalized.maxItems === 1 ? "" : "s"}.`);
    }
    const itemSchema = normalizeSchemaObject(normalized.items);
    value.forEach((item, index) => {
      errors.push(...validateAgainstSchema(item, itemSchema, `${path}[${index}]`));
    });
    return errors;
  }

  if (inferredType === "string") {
    if (typeof value !== "string") return [`${path} must be a string.`];
    if (typeof normalized.minLength === "number" && value.length < normalized.minLength) {
      errors.push(`${path} must be at least ${normalized.minLength} character${normalized.minLength === 1 ? "" : "s"}.`);
    }
    return errors;
  }

  if (inferredType === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) return [`${path} must be an integer.`];
    return validateNumericBounds(value, normalized, path);
  }

  if (inferredType === "number") {
    if (typeof value !== "number" || Number.isNaN(value)) return [`${path} must be a number.`];
    return validateNumericBounds(value, normalized, path);
  }

  if (inferredType === "boolean") {
    if (typeof value !== "boolean") return [`${path} must be a boolean.`];
    return errors;
  }

  if (inferredType === "null") {
    if (value !== null) return [`${path} must be null.`];
  }
  return errors;
}

function validateNumericBounds(value: number, schema: JsonSchema, path: string): string[] {
  const errors: string[] = [];
  if (typeof schema.minimum === "number" && value < schema.minimum) {
    errors.push(`${path} must be at least ${schema.minimum}.`);
  }
  if (typeof schema.maximum === "number" && value > schema.maximum) {
    errors.push(`${path} must be at most ${schema.maximum}.`);
  }
  return errors;
}

function inferSchemaType(schema: JsonSchema): string | undefined {
  if (schema.properties || schema.required) return "object";
  if (schema.items) return "array";
  return undefined;
}

function normalizeVariantSchema(schema: JsonSchema): JsonSchema {
  for (const key of ["oneOf", "anyOf", "allOf"] as const) {
    const variants = schema[key];
    if (Array.isArray(variants) && variants.length > 0 && isRecord(variants[0])) {
      return { ...schema, ...(variants[0] as JsonSchema) };
    }
  }
  return schema;
}

function joinPath(base: string, key: string): string {
  return base === "$" ? `$.${key}` : `${base}.${key}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
