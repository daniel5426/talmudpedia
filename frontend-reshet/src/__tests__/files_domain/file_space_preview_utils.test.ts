import { resolveFileSpacePreviewAdapter } from "@/components/admin/files/fileSpacePreviewUtils"

describe("file space preview utils", () => {
  it("detects markdown previews before generic text", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: true,
        mime_type: "text/markdown",
        path: "notes.md",
      }),
    ).toMatchObject({ id: "markdown", loadMode: "text", editorMode: "preview" })
  })

  it("detects delimited text editors before generic text", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: true,
        mime_type: "text/csv",
        path: "table.csv",
      }),
    ).toMatchObject({ id: "delimited-text", loadMode: "text", editorMode: "spreadsheet" })
  })

  it("detects plain text editors", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: true,
        mime_type: "text/plain",
        path: "notes.txt",
      }),
    ).toMatchObject({ id: "text", loadMode: "text", editorMode: "text" })
  })

  it("detects image previews", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: false,
        mime_type: "image/png",
        path: "image.png",
      }),
    ).toMatchObject({ id: "image", loadMode: "blob", editorMode: "preview" })
  })

  it("detects pdf previews", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: false,
        mime_type: "application/pdf",
        path: "guide.pdf",
      }),
    ).toMatchObject({ id: "pdf", loadMode: "blob", editorMode: "preview" })
  })

  it("detects docx previews", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: false,
        mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        path: "brief.docx",
      }),
    ).toMatchObject({ id: "docx", loadMode: "blob", editorMode: "preview" })
  })

  it("detects workbook previews", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: false,
        mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path: "sheet.xlsx",
      }),
    ).toMatchObject({ id: "workbook", loadMode: "blob", editorMode: "preview" })
  })

  it("falls back to unsupported for other binaries", () => {
    expect(
      resolveFileSpacePreviewAdapter({
        entry_type: "file",
        is_text: false,
        mime_type: "application/zip",
        path: "archive.zip",
      }),
    ).toMatchObject({ id: "unsupported", loadMode: "none", editorMode: "unsupported" })
  })
})
