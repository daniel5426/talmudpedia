import {
  parseDelimitedTextSheet,
  serializeDelimitedTextSheet,
  updateDelimitedTextCell,
} from "@/components/admin/files/fileSpaceSpreadsheetUtils"

describe("file space spreadsheet utils", () => {
  it("auto-detects semicolon-delimited csv content", () => {
    const sheet = parseDelimitedTextSheet("name;role\nAda;Editor", { path: "people.csv", mimeType: "text/csv" })

    expect(sheet.delimiter).toBe(";")
    expect(sheet.rows).toEqual([
      ["name", "role"],
      ["Ada", "Editor"],
    ])
  })

  it("round-trips delimited rows through serialization", () => {
    const serialized = serializeDelimitedTextSheet(
      [
        ["name", "role"],
        ["Ada", "Editor"],
      ],
      ",",
    )

    expect(serialized).toBe("name,role\nAda,Editor")
  })

  it("updates a single cell through the shared text source", () => {
    const nextContent = updateDelimitedTextCell("name,role\nAda,Editor", 1, 1, "Author", {
      path: "people.csv",
      mimeType: "text/csv",
    })

    expect(nextContent).toBe("name,role\nAda,Author")
  })
}
