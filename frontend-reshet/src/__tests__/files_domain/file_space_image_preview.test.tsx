import { act, fireEvent, render, screen } from "@testing-library/react"

import { FileSpaceImagePreview } from "@/components/admin/files/FileSpaceImagePreview"

describe("file space image preview", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      observe() {}
      disconnect() {}
    }

    Object.defineProperty(globalThis, "ResizeObserver", {
      writable: true,
      value: ResizeObserverMock,
    })
  })

  it("supports zooming and resetting the image view", async () => {
    render(<FileSpaceImagePreview src="blob:image" alt="Preview of image.png" />)

    const image = screen.getByAltText("Preview of image.png")
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 1200 })
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 800 })
    await act(async () => {
      fireEvent.load(image)
    })

    const zoomOutButton = screen.getByRole("button", { name: "Zoom out" })
    const zoomInButton = screen.getByRole("button", { name: "Zoom in" })
    const resetButton = screen.getByRole("button", { name: "Reset image view" })

    expect(screen.getByText("100%")).toBeInTheDocument()
    expect(zoomOutButton).toBeDisabled()
    expect(resetButton).toBeDisabled()

    fireEvent.click(zoomInButton)

    expect(screen.getByText("120%")).toBeInTheDocument()
    expect(resetButton).toBeEnabled()

    fireEvent.click(resetButton)

    expect(screen.getByText("100%")).toBeInTheDocument()
    expect(zoomOutButton).toBeDisabled()
    expect(resetButton).toBeDisabled()
  })
})
