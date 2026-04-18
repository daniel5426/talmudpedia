import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { useEffect, useRef } from "react"

import { FileSpacePdfPreview } from "@/components/admin/files/FileSpacePdfPreview"

jest.mock("react-pdf", () => {
  return {
    pdfjs: {
      version: "test",
      GlobalWorkerOptions: {},
    },
    Document: ({
      children,
      onLoadSuccess,
    }: {
      children: ReactNode
      onLoadSuccess?: (payload: { numPages: number }) => void
    }) => {
      const didReportRef = useRef(false)

      useEffect(() => {
        if (didReportRef.current) return
        didReportRef.current = true
        onLoadSuccess?.({ numPages: 4 })
      }, [onLoadSuccess])

      return <div>{children}</div>
    },
    Page: ({ pageNumber }: { pageNumber: number }) => <div>PDF Page {pageNumber}</div>,
  }
})

describe("file space pdf preview", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      constructor(private readonly callback: (entries: Array<{ contentRect: { width: number } }>) => void) {}

      observe() {
        this.callback([{ contentRect: { width: 1280 } }])
      }

      disconnect() {}
    }

    Object.defineProperty(globalThis, "ResizeObserver", {
      writable: true,
      value: ResizeObserverMock,
    })

    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      writable: true,
      value: jest.fn(),
    })
  })

  it("renders a bottom page navigator for pdf files", async () => {
    render(<FileSpacePdfPreview file={new Blob(["pdf"], { type: "application/pdf" })} />)

    expect(await screen.findByText("PDF Page 4")).toBeInTheDocument()
    expect(screen.getByLabelText("PDF preview")).toBeInTheDocument()
    expect(screen.getByLabelText("Jump to PDF page")).toHaveValue("1")
    expect(screen.getByText("/ 4")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Next page" }))

    await waitFor(() => {
      expect(screen.getByLabelText("Jump to PDF page")).toHaveValue("2")
    })
  })
})
