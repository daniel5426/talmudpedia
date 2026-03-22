import { Node } from "@xyflow/react"

import { normalizeBuilderNode, normalizeGraphSpecForSave, resolveGraphSpecVersion } from "@/components/agent-builder/graphspec"
import { AgentNodeData } from "@/components/agent-builder/types"

const buildNode = (id: string, type: string, config: Record<string, unknown> = {}): Node<AgentNodeData> => ({
  id,
  type,
  position: { x: 0, y: 0 },
  config,
  data: {
    nodeType: type as any,
    category: type === "start" || type === "end" ? "control" : "reasoning",
    displayName: type,
    config,
    inputType: "any",
    outputType: "any",
    isConfigured: true,
    hasErrors: false,
  },
} as Node<AgentNodeData>)

describe("graphspec v3 serialization", () => {
  it("always persists spec version 3.0", () => {
    const nodes = [buildNode("start", "start"), buildNode("agent", "agent", { model_id: "model-1" })]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" })

    expect(saved.spec_version).toBe("3.0")
    expect(resolveGraphSpecVersion(nodes, "2.0")).toBe("3.0")
  })

  it("hydrates default end schema config when legacy end config is empty", () => {
    const normalized = normalizeBuilderNode(buildNode("end", "end", {}))
    const config = normalized.data.config as Record<string, unknown>

    expect(config.output_schema).toBeDefined()
    expect(Array.isArray(config.output_bindings)).toBe(true)
  })

  it("roundtrips saved v3 contract nodes without serialization drift", () => {
    const rawNodes = [
      buildNode("start", "start", {
        state_variables: [{ key: "customer_name", type: "string", default_value: "Ada" }],
      }),
      buildNode("classify_1", "classify", {
        model_id: "model-1",
        input_source: { namespace: "workflow_input", key: "input_as_text", expected_type: "string" },
        categories: [{ name: "support", description: "Support requests" }],
      }),
      buildNode("set_state_1", "set_state", {
        assignments: [
          {
            key: "selected_category",
            type: "string",
            value_ref: {
              namespace: "node_output",
              node_id: "classify_1",
              key: "category",
              expected_type: "string",
            },
          },
        ],
      }),
      buildNode("end", "end", {
        output_schema: {
          name: "result",
          mode: "simple",
          schema: {
            type: "object",
            additionalProperties: false,
            properties: {
              reply: { type: "string" },
            },
            required: ["reply"],
          },
        },
        output_bindings: [
          {
            json_pointer: "/reply",
            value_ref: {
              namespace: "state",
              key: "selected_category",
              expected_type: "string",
            },
          },
        ],
      }),
    ]

    const firstHydration = rawNodes.map(normalizeBuilderNode)
    const firstSave = normalizeGraphSpecForSave(firstHydration, [])
    const secondHydration = firstSave.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const secondSave = normalizeGraphSpecForSave(secondHydration, [])

    expect(secondSave).toEqual(firstSave)
  })

  it("normalizes saved v3 special-node configs before edit and re-save", () => {
    const savedGraphNodes = [
      buildNode("start", "start", {
        state_variables: [{ name: "customer_name", type: "string", default: "Ada" }],
      }),
      buildNode("classify_1", "classify", {
        model_id: "model-1",
        input_source: {
          namespace: "workflow_input",
          key: "input_as_text",
          expected_type: "string",
          label: "Workflow Input / input_as_text",
        },
        categories: [{ name: "support", description: "Support requests" }],
      }),
      buildNode("set_state_1", "set_state", {
        assignments: [
          {
            variable: "selected_category",
            value_type: "array",
            value_ref: {
              namespace: "node_output",
              node_id: "classify_1",
              key: "category",
              expected_type: "string",
              label: "Classifier / category",
            },
          },
        ],
      }),
      buildNode("end", "end", {
        output_schema: {
          name: "result",
          mode: "simple",
          schema: {
            type: "object",
            additionalProperties: false,
            properties: { reply: { type: "string" } },
            required: ["reply"],
          },
        },
        output_bindings: [
          {
            json_pointer: "/reply",
            value_ref: {
              namespace: "state",
              key: "selected_category",
              expected_type: "string",
              label: "State / selected_category",
            },
          },
        ],
      }),
    ]

    const hydrated = savedGraphNodes.map(normalizeBuilderNode)
    const startConfig = hydrated[0].data.config as Record<string, unknown>
    const setStateConfig = hydrated[2].data.config as Record<string, unknown>

    expect(startConfig.state_variables).toEqual([
      { key: "customer_name", type: "string", default_value: "Ada" },
    ])
    expect(setStateConfig.assignments).toEqual([
      {
        key: "selected_category",
        type: "list",
        value_ref: {
          namespace: "node_output",
          node_id: "classify_1",
          key: "category",
          expected_type: "string",
          label: "Classifier / category",
        },
      },
    ])

    const edited = hydrated.map((node) => {
      if (node.id !== "end") return node
      return {
        ...node,
        config: {
          ...(node.config as Record<string, unknown>),
          output_bindings: [
            {
              json_pointer: "/reply",
              value_ref: {
                namespace: "workflow_input",
                key: "input_as_text",
                expected_type: "string",
              },
            },
          ],
        },
        data: {
          ...node.data,
          config: {
            ...(node.data.config as Record<string, unknown>),
            output_bindings: [
              {
                json_pointer: "/reply",
                value_ref: {
                  namespace: "workflow_input",
                  key: "input_as_text",
                  expected_type: "string",
                },
              },
            ],
          },
        },
      } as Node<AgentNodeData>
    })

    const saved = normalizeGraphSpecForSave(edited, [])
    const reopened = saved.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const resaved = normalizeGraphSpecForSave(reopened, [])

    expect(resaved).toEqual(saved)
  })
})
