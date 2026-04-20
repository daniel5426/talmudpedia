import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import { FileSpaceWorkbookPreview } from "@/components/admin/files/FileSpaceWorkbookPreview"

jest.mock("xlsx", () => ({
  read: jest.fn(() => ({
    SheetNames: ["Sheet 1", "Summary"],
    Sheets: {
      "Sheet 1": { __rows: [["name", "role"], ["Ada", "Editor"]] },
      Summary: { __rows: [["count"], ["2"]] },
    },
  })),
  utils: {
    sheet_to_json: jest.fn((sheet: { __rows: string[][] }) => sheet.__rows),
  },
}))

describe("file space workbook preview", () => {
  it("renders workbook tabs and read-only sheet values", async () => {
    render(<FileSpaceWorkbookPreview file={new Blob(["xlsx"], { type: "application/vnd.ms-excel" })} />)

    expect(await screen.findByRole("button", { name: "Sheet 1" })).toBeInTheDocument()
    expect(screen.getByText("Ada")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Summary" }))

    await waitFor(() => {
      expect(screen.getByText("count")).toBeInTheDocument()
      expect(screen.getByText("2")).toBeInTheDocument()
    })

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })
})
