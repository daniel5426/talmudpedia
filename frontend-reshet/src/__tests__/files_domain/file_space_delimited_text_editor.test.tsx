import { fireEvent, render, screen } from "@testing-library/react"

import { FileSpaceDelimitedTextEditor } from "@/components/admin/files/FileSpaceDelimitedTextEditor"

describe("file space delimited text editor", () => {
  it("edits spreadsheet cells through the text source", () => {
    const onChange = jest.fn()

    render(
      <FileSpaceDelimitedTextEditor
        path="people.csv"
        mimeType="text/csv"
        value={"name,role\nAda,Editor"}
        mode="grid"
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByLabelText("Cell B2"), { target: { value: "Author" } })

    expect(onChange).toHaveBeenCalledWith("name,role\nAda,Author")
  })

  it("supports switching between grid and raw text modes", () => {
    const onChange = jest.fn()

    const { rerender } = render(
      <FileSpaceDelimitedTextEditor
        path="people.csv"
        mimeType="text/csv"
        value={"name,role\nAda,Editor"}
        mode="grid"
        onChange={onChange}
      />,
    )

    rerender(
      <FileSpaceDelimitedTextEditor
        path="people.csv"
        mimeType="text/csv"
        value={"name,role\nAda,Editor"}
        mode="raw"
        onChange={onChange}
      />,
    )

    expect(screen.getByRole("textbox")).toHaveValue("name,role\nAda,Editor")

    rerender(
      <FileSpaceDelimitedTextEditor
        path="people.csv"
        mimeType="text/csv"
        value={"name,role\nAda,Editor"}
        mode="grid"
        onChange={onChange}
      />,
    )

    expect(screen.getByLabelText("Cell B2")).toBeInTheDocument()
  })
}
