import type { FileSpaceEntry } from "@/services"

export type FileSpacePreviewKind = "text-editable" | "image" | "pdf" | "docx" | "unsupported"

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"])
const DOCX_MIME_TYPES = new Set([
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-word.document.macroenabled.12",
])

export function getFileExtension(path: string): string {
  const filename = String(path || "").split("/").pop() || ""
  const extension = filename.includes(".") ? filename.split(".").pop() || "" : ""
  return extension.trim().toLowerCase()
}

export function resolveFileSpacePreviewKind(
  entry: Pick<FileSpaceEntry, "entry_type" | "is_text" | "mime_type" | "path">,
): FileSpacePreviewKind {
  if (entry.entry_type !== "file") return "unsupported"
  if (entry.is_text) return "text-editable"

  const mimeType = String(entry.mime_type || "").trim().toLowerCase()
  const extension = getFileExtension(entry.path)

  if (mimeType.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) {
    return "image"
  }

  if (mimeType === "application/pdf" || extension === "pdf") {
    return "pdf"
  }

  if (DOCX_MIME_TYPES.has(mimeType) || extension === "docx") {
    return "docx"
  }

  return "unsupported"
}
