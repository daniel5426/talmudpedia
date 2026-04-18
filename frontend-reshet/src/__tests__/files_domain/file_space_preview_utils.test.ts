import { resolveFileSpacePreviewKind } from "@/components/admin/files/fileSpacePreviewUtils"

describe("file space preview utils", () => {
  it("detects editable text files", () => {
    expect(
      resolveFileSpacePreviewKind({
        entry_type: "file",
        is_text: true,
        mime_type: "text/markdown",
        path: "notes.md",
      }),
    ).toBe("text-editable")
  })

  it("detects image previews", () => {
    expect(
      resolveFileSpacePreviewKind({
        entry_type: "file",
        is_text: false,
        mime_type: "image/png",
        path: "image.png",
      }),
    ).toBe("image")
  })

  it("detects pdf previews", () => {
    expect(
      resolveFileSpacePreviewKind({
        entry_type: "file",
        is_text: false,
        mime_type: "application/pdf",
        path: "guide.pdf",
      }),
    ).toBe("pdf")
  })

  it("detects docx previews", () => {
    expect(
      resolveFileSpacePreviewKind({
        entry_type: "file",
        is_text: false,
        mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        path: "brief.docx",
      }),
    ).toBe("docx")
  })

  it("falls back to unsupported for other binaries", () => {
    expect(
      resolveFileSpacePreviewKind({
        entry_type: "file",
        is_text: false,
        mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path: "sheet.xlsx",
      }),
    ).toBe("unsupported")
  })
})
