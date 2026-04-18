import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { FileSpaceDocxPreview } from "@/components/admin/files/FileSpaceDocxPreview"

const renderAsyncMock = jest.fn()

jest.mock("docx-preview", () => ({
  renderAsync: (...args: unknown[]) => renderAsyncMock(...args),
}))

describe("file space docx preview", () => {
  beforeAll(() => {
    Object.defineProperty(globalThis, "requestAnimationFrame", {
      writable: true,
      value: (callback: FrameRequestCallback) => callback(0),
    })
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      writable: true,
      value: jest.fn(),
    })
  })

  beforeEach(() => {
    jest.clearAllMocks()
    renderAsyncMock.mockImplementation(async (_data, container: HTMLElement) => {
      for (let page = 1; page <= 2; page += 1) {
        const section = document.createElement("section")
        section.className = "file-space-docx"
        section.textContent = `DOCX Preview ${page}`
        Object.defineProperty(section, "offsetTop", {
          configurable: true,
          value: (page - 1) * 600,
        })
        container.appendChild(section)
      }
      return {}
    })
  })

  it("renders bottom zoom and page controls for docx files", async () => {
    render(<FileSpaceDocxPreview data={new ArrayBuffer(16)} />)

    expect(await screen.findByText("DOCX Preview 2")).toBeInTheDocument()
    expect(screen.getByLabelText("Document preview")).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByLabelText("Jump to document page")).toHaveValue("1")
    })
    expect(screen.getByText((content) => content.includes("/ 2"))).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }))

    expect(screen.getByText("120%")).toBeInTheDocument()
    expect(screen.getByTestId("docx-zoom-layer").className).toContain("cursor-grab")

    fireEvent.click(screen.getByRole("button", { name: "Next document page" }))

    await waitFor(() => {
      expect(screen.getByLabelText("Jump to document page")).toHaveValue("2")
    })
  })
})
