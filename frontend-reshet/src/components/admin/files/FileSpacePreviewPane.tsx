"use client"

import { useEffect, useState, type ReactNode } from "react"
import { FileIcon, Loader2, TriangleAlert } from "lucide-react"

import { fileSpacesService, type FileSpaceEntry } from "@/services"

import { FileSpaceDocxPreview } from "./FileSpaceDocxPreview"
import { FileSpaceImagePreview } from "./FileSpaceImagePreview"
import { FileSpacePdfPreview } from "./FileSpacePdfPreview"
import { resolveFileSpacePreviewKind } from "./fileSpacePreviewUtils"

type FileSpacePreviewPaneProps = {
  spaceId: string
  entry: FileSpaceEntry
}

type PreviewState =
  | { status: "idle"; blob: null; objectUrl: null; docxData: null; error: null }
  | { status: "loading"; blob: null; objectUrl: null; docxData: null; error: null }
  | { status: "ready"; blob: Blob; objectUrl: string | null; docxData: ArrayBuffer | null; error: null }
  | { status: "error"; blob: null; objectUrl: null; docxData: null; error: string }

function PreviewMessage({
  icon,
  title,
  description,
}: {
  icon: ReactNode
  title: string
  description: string
}) {
  return (
    <div className="flex h-full min-h-[18rem] flex-col items-center justify-center px-6 text-center">
      <div className="mb-3 text-muted-foreground/50">{icon}</div>
      <p className="text-sm font-medium text-muted-foreground/80">{title}</p>
      <p className="mt-1 max-w-md text-xs text-muted-foreground/60">{description}</p>
    </div>
  )
}

export function FileSpacePreviewPane({ spaceId, entry }: FileSpacePreviewPaneProps) {
  const previewKind = resolveFileSpacePreviewKind(entry)
  const [previewState, setPreviewState] = useState<PreviewState>({
    status: "idle",
    blob: null,
    objectUrl: null,
    docxData: null,
    error: null,
  })

  useEffect(() => {
    if (previewKind === "unsupported" || previewKind === "text-editable") {
      return
    }

    let disposed = false
    let nextObjectUrl: string | null = null

    const loadPreview = async () => {
      setPreviewState({ status: "loading", blob: null, objectUrl: null, docxData: null, error: null })

      try {
        const blob = await fileSpacesService.fetchBlob(spaceId, entry.path)
        if (disposed) return

        if (previewKind === "docx") {
          const docxData = await blob.arrayBuffer()
          if (disposed) return
          setPreviewState({ status: "ready", blob, objectUrl: null, docxData, error: null })
          return
        }

        nextObjectUrl = previewKind === "image" ? URL.createObjectURL(blob) : null
        if (disposed && nextObjectUrl) {
          URL.revokeObjectURL(nextObjectUrl)
          return
        }
        setPreviewState({ status: "ready", blob, objectUrl: nextObjectUrl, docxData: null, error: null })
      } catch (err) {
        if (disposed) return
        console.error(err)
        setPreviewState({
          status: "error",
          blob: null,
          objectUrl: null,
          docxData: null,
          error: "Failed to load file preview.",
        })
      }
    }

    void loadPreview()

    return () => {
      disposed = true
      if (nextObjectUrl) {
        URL.revokeObjectURL(nextObjectUrl)
      }
    }
  }, [entry.path, previewKind, spaceId])

  return (
    <div className="relative flex h-full w-full flex-col">
      <div className="flex-1 overflow-hidden px-5 py-4">
        {previewKind === "unsupported" ? (
          <PreviewMessage
            icon={<FileIcon className="h-10 w-10" />}
            title="Preview unavailable"
            description={`This file type is not supported in-app yet.${entry.mime_type ? ` MIME type: ${entry.mime_type}.` : ""}`}
          />
        ) : previewState.status === "loading" ? (
          <PreviewMessage
            icon={<Loader2 className="h-10 w-10 animate-spin" />}
            title="Loading preview"
            description={`Fetching ${entry.name}...`}
          />
        ) : previewState.status === "error" ? (
          <PreviewMessage
            icon={<TriangleAlert className="h-10 w-10" />}
            title="Preview failed"
            description={previewState.error}
          />
        ) : previewState.status === "ready" && previewKind === "image" && previewState.objectUrl ? (
          <FileSpaceImagePreview
            key={previewState.objectUrl}
            src={previewState.objectUrl}
            alt={`Preview of ${entry.name}`}
          />
        ) : previewState.status === "ready" && previewKind === "pdf" ? (
          <div className="h-full w-full">
            <FileSpacePdfPreview file={previewState.blob} />
          </div>
        ) : previewState.status === "ready" && previewKind === "docx" && previewState.docxData ? (
          <div className="h-full w-full">
            <FileSpaceDocxPreview key={entry.path} data={previewState.docxData} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
