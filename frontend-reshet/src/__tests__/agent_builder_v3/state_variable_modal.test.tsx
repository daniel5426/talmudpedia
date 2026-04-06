import type { ReactElement } from "react"
import { fireEvent, render, screen } from "@testing-library/react"

import { StartNodeSettings } from "@/components/agent-builder/ConfigPanelSpecialized"
import { DirectionProvider } from "@/components/direction-provider"

function renderWithDirection(ui: ReactElement) {
  return render(<DirectionProvider>{ui}</DirectionProvider>)
}

describe("state variable modal", () => {
  it("uses a boolean select instead of free text", () => {
    const onChange = jest.fn()

    renderWithDirection(
      <StartNodeSettings
        workflowContract={{ inputs: [] }}
        stateContract={{ variables: [] }}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /add/i }))
    fireEvent.click(screen.getByRole("button", { name: /boolean/i }))
    fireEvent.change(screen.getByPlaceholderText("name"), { target: { value: "is_enabled" } })
    fireEvent.click(screen.getByRole("combobox"))
    fireEvent.click(screen.getByText("true"))
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }))

    expect(onChange).toHaveBeenLastCalledWith({
      workflowContract: { inputs: [] },
      stateContract: {
        variables: [{ key: "is_enabled", type: "boolean", default_value: true }],
      },
    })
  })

  it("builds list defaults as entered tags", () => {
    const onChange = jest.fn()

    renderWithDirection(
      <StartNodeSettings
        workflowContract={{ inputs: [] }}
        stateContract={{ variables: [] }}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /add/i }))
    fireEvent.click(screen.getByRole("button", { name: /list/i }))
    fireEvent.change(screen.getByPlaceholderText("name"), { target: { value: "tags" } })

    const tagInput = screen.getByPlaceholderText("Type a value and press Enter")
    fireEvent.change(tagInput, { target: { value: "alpha" } })
    fireEvent.keyDown(tagInput, { key: "Enter", code: "Enter" })
    fireEvent.change(tagInput, { target: { value: "beta" } })
    fireEvent.keyDown(tagInput, { key: "Enter", code: "Enter" })

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }))

    expect(onChange).toHaveBeenLastCalledWith({
      workflowContract: { inputs: [] },
      stateContract: {
        variables: [{ key: "tags", type: "list", default_value: ["alpha", "beta"] }],
      },
    })
  })

  it("shows a new property row when adding schema properties for object state variables", () => {
    renderWithDirection(
      <StartNodeSettings
        workflowContract={{ inputs: [] }}
        stateContract={{ variables: [] }}
        onChange={jest.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /add/i }))
    fireEvent.click(screen.getByRole("button", { name: /object/i }))
    fireEvent.click(screen.getByRole("button", { name: /schema/i }))
    fireEvent.click(screen.getByRole("button", { name: /^add property$/i }))

    expect(screen.getByPlaceholderText("property name")).toBeInTheDocument()
  })

  it("blocks saving duplicate state variable keys in the modal", () => {
    const onChange = jest.fn()

    renderWithDirection(
      <StartNodeSettings
        workflowContract={{ inputs: [] }}
        stateContract={{ variables: [{ key: "test", type: "string" }] }}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /add/i }))
    fireEvent.change(screen.getByPlaceholderText("name"), { target: { value: "test" } })

    expect(screen.getByText("A state variable with this key already exists.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled()

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }))

    expect(onChange).not.toHaveBeenCalled()
  })
})
