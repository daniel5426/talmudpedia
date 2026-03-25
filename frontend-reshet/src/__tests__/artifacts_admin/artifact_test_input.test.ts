import {
  buildArtifactTestInputJson,
  resolveArtifactInputSchema,
  validateArtifactTestInput,
} from "@/services/artifactTestInput";

describe("artifactTestInput", () => {
  it("builds example input JSON from the active contract input schema", () => {
    const schema = resolveArtifactInputSchema("tool_impl", {
      toolContract: {
        input_schema: {
          type: "object",
          required: ["query", "limit", "filters"],
          properties: {
            query: { type: "string", example: "rashi on berakhot" },
            limit: { type: "integer", minimum: 1 },
            filters: {
              type: "array",
              items: {
                type: "object",
                required: ["field", "value"],
                properties: {
                  field: { type: "string", enum: ["masechet", "topic"] },
                  value: { type: "string" },
                },
              },
            },
          },
        },
        output_schema: {},
        side_effects: [],
        execution_mode: "interactive",
        tool_ui: {},
      },
    });

    expect(JSON.parse(buildArtifactTestInputJson(schema))).toEqual({
      query: "rashi on berakhot",
      limit: 1,
      filters: [{ field: "masechet", value: "" }],
    });
  });

  it("ignores wrapped legacy contract payload shapes", () => {
    const schema = resolveArtifactInputSchema("tool_impl", {
      toolContract: {
        tool_contract: {
          input_schema: {
            type: "object",
            required: ["client_id"],
            properties: {
              client_id: { type: "string" },
              date_from: { type: "string" },
            },
            additionalProperties: false,
          },
        },
      } as never,
    });

    expect(schema).toEqual({});
  });

  it("returns validation errors for missing and mistyped fields", () => {
    const errors = validateArtifactTestInput(
      { query: 123, filters: [] },
      {
        type: "object",
        required: ["query", "limit"],
        properties: {
          query: { type: "string" },
          limit: { type: "integer", minimum: 1 },
          filters: { type: "array", minItems: 1, items: { type: "string" } },
        },
      },
    );

    expect(errors).toEqual([
      "$.limit is required.",
      "$.query must be a string.",
      "$.filters must contain at least 1 item.",
    ]);
  });

  it("accepts valid payloads for simple schemas", () => {
    expect(
      validateArtifactTestInput(
        { text: "hello", metadata: {} },
        {
          type: "object",
          required: ["text"],
          properties: {
            text: { type: "string", minLength: 1 },
            metadata: { type: "object", additionalProperties: true },
          },
        },
      ),
    ).toEqual([]);
  });
});
