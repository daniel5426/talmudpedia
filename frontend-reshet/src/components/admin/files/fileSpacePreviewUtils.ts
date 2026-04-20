import type { FileSpaceEntry } from "@/services"

export type FileSpacePreviewAdapterId =
  | "text"
  | "markdown"
  | "delimited-text"
  | "image"
  | "pdf"
  | "docx"
  | "workbook"
  | "unsupported"

export type FileSpacePreviewLoadMode = "none" | "text" | "blob"

export type FileSpacePreviewAdapter = {
  id: FileSpacePreviewAdapterId
  loadMode: FileSpacePreviewLoadMode
  editorMode: "text" | "spreadsheet" | "preview" | "unsupported"
}

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"])
const DOCX_MIME_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-word.document.macroenabled.12",
])
const DELIMITED_EXTENSIONS = new Set(["csv", "tsv"])
const DELIMITED_MIME_TYPES = new Set([
  "text/csv",
  "application/csv",
  "text/tab-separated-values",
  "application/tab-separated-values",
  "text/tsv",
])
const MARKDOWN_EXTENSIONS = new Set(["md", "markdown", "mdown"])
const MARKDOWN_MIME_TYPES = new Set(["text/markdown", "text/x-markdown", "application/markdown"])
const WORKBOOK_EXTENSIONS = new Set(["xlsx", "xls"])
const WORKBOOK_MIME_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "application/vnd.ms-excel.sheet.macroenabled.12",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
])

const TEXT_ADAPTER: FileSpacePreviewAdapter = {
  id: "text",
  loadMode: "text",
  editorMode: "text",
}

const DELIMITED_TEXT_ADAPTER: FileSpacePreviewAdapter = {
  id: "delimited-text",
  loadMode: "text",
  editorMode: "spreadsheet",
}

const MARKDOWN_ADAPTER: FileSpacePreviewAdapter = {
  id: "markdown",
  loadMode: "text",
  editorMode: "preview",
}

const IMAGE_ADAPTER: FileSpacePreviewAdapter = {
  id: "image",
  loadMode: "blob",
  editorMode: "preview",
}

const PDF_ADAPTER: FileSpacePreviewAdapter = {
  id: "pdf",
  loadMode: "blob",
  editorMode: "preview",
}

const DOCX_ADAPTER: FileSpacePreviewAdapter = {
  id: "docx",
  loadMode: "blob",
  editorMode: "preview",
}

const WORKBOOK_ADAPTER: FileSpacePreviewAdapter = {
  id: "workbook",
  loadMode: "blob",
  editorMode: "preview",
}

const UNSUPPORTED_ADAPTER: FileSpacePreviewAdapter = {
  id: "unsupported",
  loadMode: "none",
  editorMode: "unsupported",
}

export function getFileExtension(path: string): string {
  const filename = String(path || "").split("/").pop() || ""
  const extension = filename.includes(".") ? filename.split(".").pop() || "" : ""
  return extension.trim().toLowerCase()
}

export function resolveFileSpacePreviewAdapter(
  entry: Pick<FileSpaceEntry, "entry_type" | "is_text" | "mime_type" | "path">,
): FileSpacePreviewAdapter {
  if (entry.entry_type !== "file") return UNSUPPORTED_ADAPTER

  const mimeType = String(entry.mime_type || "").trim().toLowerCase()
  const extension = getFileExtension(entry.path)

  if (entry.is_text && (DELIMITED_EXTENSIONS.has(extension) || DELIMITED_MIME_TYPES.has(mimeType))) {
    return DELIMITED_TEXT_ADAPTER
  }

  if (entry.is_text && (MARKDOWN_EXTENSIONS.has(extension) || MARKDOWN_MIME_TYPES.has(mimeType))) {
    return MARKDOWN_ADAPTER
  }

  if (entry.is_text) {
    return TEXT_ADAPTER
  }

  if (mimeType.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) {
    return IMAGE_ADAPTER
  }

  if (mimeType === "application/pdf" || extension === "pdf") {
    return PDF_ADAPTER
  }

  if (DOCX_MIME_TYPES.has(mimeType) || extension === "docx") {
    return DOCX_ADAPTER
  }

  if (WORKBOOK_MIME_TYPES.has(mimeType) || WORKBOOK_EXTENSIONS.has(extension)) {
    return WORKBOOK_ADAPTER
  }

  return UNSUPPORTED_ADAPTER
}
