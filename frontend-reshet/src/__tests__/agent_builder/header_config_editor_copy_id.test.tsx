import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { HeaderConfigEditor } from "@/components/builder/HeaderConfigEditor"

const clipboardWriteTextMock = jest.fn()

jest.mock("motion/react", () => ({
  motion: {
    div: ({ children, initial, animate, transition, ...props }: any) => <div {...props}>{children}</div>,
  },
}))

describe("header config editor copy id", () => {
  beforeEach(() => {
    jest.clearAllMocks()
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWriteTextMock,
      },
    })
    clipboardWriteTextMock.mockResolvedValue(undefined)
  })

  it("renders the agent id and copies it from the details panel", async () => {
    render(
      <HeaderConfigEditor
        name="Research Assistant"
        description="Handles research requests."
        onNameChange={jest.fn()}
        onDescriptionChange={jest.fn()}
        identifier="agent-123"
        identifierLabel="Agent ID"
        defaultOpen
      />
    )

    expect(screen.getByText("agent-123")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Copy agent ID" }))

    await waitFor(() => {
      expect(clipboardWriteTextMock).toHaveBeenCalledWith("agent-123")
    })
  })
})
