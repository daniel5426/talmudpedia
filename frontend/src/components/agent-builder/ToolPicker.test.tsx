import React, { useState } from "react"
import { render, screen, fireEvent } from "@testing-library/react"
import { ToolPicker } from "@/components/agent-builder/ToolPicker"
import { ToolDefinition } from "@/services/agent"

const makeTool = (overrides: Partial<ToolDefinition>): ToolDefinition => ({
  id: "tool-1",
  name: "Alpha Tool",
  slug: "alpha-tool",
  description: "Alpha",
  input_schema: {},
  output_schema: {},
  implementation_type: "http",
  implementation_config: {},
  execution_config: {},
  version: "1.0.0",
  status: "published",
  tenant_id: "tenant-1",
  created_at: "",
  updated_at: "",
  published_at: null,
  ...overrides,
})

function Wrapper({ tools }: { tools: ToolDefinition[] }) {
  const [value, setValue] = useState<string[]>([])
  return <ToolPicker tools={tools} value={value} onChange={setValue} open={true} onOpenChange={() => undefined} />
}

test("ToolPicker filters by search query", () => {
  const tools = [
    makeTool({ id: "1", name: "Alpha Tool", slug: "alpha-tool" }),
    makeTool({ id: "2", name: "Beta Tool", slug: "beta-tool" }),
  ]

  render(<Wrapper tools={tools} />)

  const input = screen.getByPlaceholderText("Search tools...")
  fireEvent.change(input, { target: { value: "Beta" } })

  expect(screen.queryByText("Alpha Tool")).toBeNull()
  expect(screen.getByText("Beta Tool")).toBeInTheDocument()
})

test("ToolPicker filters by bucket and subtype", () => {
  const tools = [
    makeTool({ id: "1", name: "Alpha Tool", slug: "alpha-tool", implementation_type: "http" }),
    makeTool({ id: "2", name: "Artifact Tool", slug: "artifact-tool", implementation_type: "artifact", artifact_id: "custom/tool" }),
  ]

  render(<Wrapper tools={tools} />)

  const artifactButtons = screen.getAllByRole("button", { name: "Artifact" })
  fireEvent.click(artifactButtons[0])
  expect(screen.queryByText("Alpha Tool")).toBeNull()
  expect(screen.getByText("Artifact Tool")).toBeInTheDocument()

  fireEvent.click(artifactButtons[0])
  fireEvent.click(screen.getByRole("button", { name: "HTTP" }))
  expect(screen.getByText("Alpha Tool")).toBeInTheDocument()
})

test("ToolPicker selection toggles and clears", () => {
  const tools = [makeTool({ id: "1", name: "Alpha Tool" })]
  render(<Wrapper tools={tools} />)

  const checkbox = screen.getByLabelText("Alpha Tool")
  fireEvent.click(checkbox)
  expect(screen.getByText("1 selected")).toBeInTheDocument()

  fireEvent.click(screen.getByRole("button", { name: "Clear all" }))
  expect(screen.getByText("0 selected")).toBeInTheDocument()
})
