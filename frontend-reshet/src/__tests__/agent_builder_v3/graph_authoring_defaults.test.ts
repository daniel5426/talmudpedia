import { applySchemaDefaults } from "@/services/graph-authoring"

describe("graph authoring defaults", () => {
  it("applies nested schema defaults without inventing extra fields", () => {
    expect(
      applySchemaDefaults(
        {
          type: "object",
          properties: {
            output_schema: {
              type: "object",
              properties: {
                name: { type: "string", default: "workflow_result" },
                mode: { type: "string", default: "simple" },
              },
            },
            untouched: {
              type: "object",
              properties: {
                value: { type: "string" },
              },
            },
          },
        },
        {}
      )
    ).toEqual({
      output_schema: {
        name: "workflow_result",
        mode: "simple",
      },
    })
  })
})
