import { Node } from "@xyflow/react"

import { normalizeBuilderNode, normalizeGraphDefinition, normalizeGraphSpecForSave, resolveGraphSpecVersion } from "@/components/agent-builder/graphspec"
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

describe("graphspec v4 serialization", () => {
  it("normalizes branch configs to opaque ids", () => {
    const normalized = normalizeGraphDefinition({
      spec_version: "4.0",
      nodes: [
        buildNode("classify_1", "classify", {
          model_id: "model-1",
          categories: [{ name: "support" }, { name: "sales" }],
        }),
        buildNode("if_1", "if_else", {
          conditions: [{ name: "has_profile", expression: "true" }],
        }),
      ],
      edges: [],
    })

    const classifyConfig = normalized.nodes[0].config as Record<string, any>
    const ifConfig = normalized.nodes[1].config as Record<string, any>

    expect(classifyConfig.categories[0].id).toMatch(/^branch_/)
    expect(classifyConfig.categories[1].id).toMatch(/^branch_/)
    expect(ifConfig.conditions[0].id).toMatch(/^branch_/)
  })

  it("always persists spec version 4.0", () => {
    const nodes = [buildNode("start", "start"), buildNode("agent", "agent", { model_id: "model-1" })]
    const saved = normalizeGraphSpecForSave(nodes, [], { specVersion: "1.0" })

    expect(saved.spec_version).toBe("4.0")
    expect(resolveGraphSpecVersion(nodes, "2.0")).toBe("4.0")
    expect(saved.workflow_contract?.inputs.map((item) => item.key)).toEqual([
      "text",
      "files",
      "audio",
      "images",
    ])
    expect(saved.state_contract?.variables).toEqual([])
  })

  it("hydrates default end schema config when legacy end config is empty", () => {
    const normalized = normalizeBuilderNode(buildNode("end", "end", {}))
    const config = normalized.data.config as Record<string, unknown>

    expect(config.output_schema).toBeDefined()
    expect(Array.isArray(config.output_bindings)).toBe(true)
  })

  it("roundtrips saved v4 contract nodes without serialization drift", () => {
    const rawGraph = normalizeGraphDefinition({
      spec_version: "4.0",
      state_contract: {
        variables: [{ key: "customer_name", type: "string", default_value: "Ada" }],
      },
      workflow_contract: {
        inputs: [{ key: "text", type: "string", required: false, label: "Text" }],
      },
      nodes: [
        buildNode("start", "start", {}),
      buildNode("classify_1", "classify", {
        model_id: "model-1",
        input_source: { namespace: "workflow_input", key: "text", expected_type: "string" },
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
      ],
      edges: [],
    })

    const firstHydration = rawGraph.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const firstSave = normalizeGraphSpecForSave(firstHydration, [], {
      workflowContract: rawGraph.workflow_contract,
      stateContract: rawGraph.state_contract,
    })
    const secondHydration = firstSave.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const secondSave = normalizeGraphSpecForSave(secondHydration, [], {
      workflowContract: firstSave.workflow_contract,
      stateContract: firstSave.state_contract,
    })

    expect(secondSave).toEqual(firstSave)
  })

  it("normalizes legacy start-owned state into the v4 top-level contract before edit and re-save", () => {
    const savedGraph = normalizeGraphDefinition({
      spec_version: "3.0",
      nodes: [
        buildNode("start", "start", {
          state_variables: [{ name: "customer_name", type: "string", default: "Ada" }],
        }),
      buildNode("classify_1", "classify", {
        model_id: "model-1",
        input_source: {
          namespace: "workflow_input",
          key: "text",
          expected_type: "string",
          label: "Workflow Input / text",
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
      ],
      edges: [],
    })

    const hydrated = savedGraph.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const startConfig = hydrated[0].data.config as Record<string, unknown>
    const setStateConfig = hydrated[2].data.config as Record<string, unknown>

    expect(startConfig.state_variables).toEqual([])
    expect(savedGraph.state_contract?.variables).toEqual([
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
          ...((node as unknown as { config?: Record<string, unknown> }).config || {}),
          output_bindings: [
            {
              json_pointer: "/reply",
              value_ref: {
                namespace: "workflow_input",
                key: "text",
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
                  key: "text",
                  expected_type: "string",
                },
              },
            ],
          },
        },
      } as Node<AgentNodeData>
    })

    const saved = normalizeGraphSpecForSave(edited, [], {
      workflowContract: savedGraph.workflow_contract,
      stateContract: savedGraph.state_contract,
    })
    const reopened = saved.nodes.map((node) => normalizeBuilderNode(node as Node<AgentNodeData>))
    const resaved = normalizeGraphSpecForSave(reopened, [], {
      workflowContract: saved.workflow_contract,
      stateContract: saved.state_contract,
    })

    expect(resaved).toEqual(saved)
  })
})
