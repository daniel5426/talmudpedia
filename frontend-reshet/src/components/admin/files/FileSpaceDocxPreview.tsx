"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, Minus, Plus, RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"

type FileSpaceDocxPreviewProps = {
  data: ArrayBuffer
}

const MIN_ZOOM = 0.8
const MAX_ZOOM = 2

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function clampPage(page: number, total: number) {
  return Math.min(Math.max(page, 1), Math.max(total, 1))
}

export function FileSpaceDocxPreview({ data }: FileSpaceDocxPreviewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    startTranslateX: number
    startTranslateY: number
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [translate, setTranslate] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [pageCount, setPageCount] = useState(1)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageInput, setPageInput] = useState("1")

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let cancelled = false
    container.innerHTML = ""
    setError(null)

    void import("docx-preview")
      .then(async ({ renderAsync }) => {
        await renderAsync(data, container, container, {
          className: "file-space-docx",
          useBase64URL: true,
        })

        if (cancelled) return

        requestAnimationFrame(() => {
          if (cancelled) return
          const pages = container.querySelectorAll<HTMLElement>("section.file-space-docx")
          const nextPageCount = Math.max(pages.length, 1)
          setPageCount(nextPageCount)
          setCurrentPage(1)
          setPageInput("1")
        })
      })
      .catch((err) => {
        if (cancelled) return
        console.error(err)
        setError("Failed to render document preview.")
      })

    return () => {
      cancelled = true
      container.innerHTML = ""
    }
  }, [data])

  useEffect(() => {
    setZoom(1)
    setTranslate({ x: 0, y: 0 })
    setCurrentPage(1)
    setPageInput("1")
  }, [data])

  useEffect(() => {
    if (zoom <= 1) {
      setTranslate({ x: 0, y: 0 })
      setIsDragging(false)
      dragStateRef.current = null
    }
  }, [zoom])

  useEffect(() => {
    setPageInput(String(currentPage))
  }, [currentPage])

  const jumpToPage = (requestedPage: number) => {
    const nextPage = clampPage(requestedPage, pageCount)
    const container = containerRef.current
    const scrollNode = scrollRef.current
    const target = container?.querySelector<HTMLElement>(`section.file-space-docx:nth-of-type(${nextPage})`)

    if (scrollNode && target) {
      setTranslate({ x: 0, y: 0 })
      scrollNode.scrollTo({
        top: Math.max(target.offsetTop * zoom - 8, 0),
        behavior: "smooth",
      })
    }

    setCurrentPage(nextPage)
    setPageInput(String(nextPage))
  }

  if (error) {
    return (
      <div className="flex h-full min-h-[16rem] items-center justify-center rounded-xl border border-dashed border-border/60 bg-muted/20 px-6 text-center text-sm text-muted-foreground">
        {error}
      </div>
    )
  }

  return (
    <div className="relative h-full min-h-[24rem] overflow-hidden rounded-2xl bg-[linear-gradient(180deg,hsl(var(--background)),hsl(var(--muted)/0.1))] shadow-[inset_0_1px_0_hsl(var(--background)),0_1px_2px_rgba(15,23,42,0.04)]">
      <div
        ref={scrollRef}
        aria-label="Document preview"
        className="h-full overflow-auto overscroll-contain px-6 pb-24 pt-6"
        onScroll={(event) => {
          const container = containerRef.current
          if (!container) return
          const pages = Array.from(container.querySelectorAll<HTMLElement>("section.file-space-docx"))
          if (!pages.length) return

          const threshold = event.currentTarget.scrollTop + 24
          const nextCurrentPage =
            pages.reduce((page, element, index) => {
              const visualTop = element.offsetTop * zoom + translate.y
              return visualTop <= threshold ? index + 1 : page
            }, 1) || 1

          if (nextCurrentPage !== currentPage) {
            setCurrentPage(nextCurrentPage)
          }
        }}
      >
        <div className="flex min-h-full justify-center">
          <div
            data-testid="docx-zoom-layer"
            className={zoom > 1 ? (isDragging ? "cursor-grabbing" : "cursor-grab") : undefined}
            style={{
              transform: `translate(${translate.x}px, ${translate.y}px) scale(${zoom})`,
              transformOrigin: "top center",
            }}
            onPointerDown={(event) => {
              if (zoom <= 1 || event.button !== 0) return
              event.preventDefault()
              dragStateRef.current = {
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                startTranslateX: translate.x,
                startTranslateY: translate.y,
              }
              setIsDragging(true)
              if (event.currentTarget.setPointerCapture) {
                event.currentTarget.setPointerCapture(event.pointerId)
              }
            }}
            onPointerMove={(event) => {
              const dragState = dragStateRef.current
              if (!dragState || dragState.pointerId !== event.pointerId) return
              setTranslate({
                x: dragState.startTranslateX + (event.clientX - dragState.startX),
                y: dragState.startTranslateY + (event.clientY - dragState.startY),
              })
            }}
            onPointerUp={(event) => {
              if (dragStateRef.current?.pointerId !== event.pointerId) return
              dragStateRef.current = null
              setIsDragging(false)
              if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId)
              }
            }}
            onPointerCancel={(event) => {
              if (dragStateRef.current?.pointerId !== event.pointerId) return
              dragStateRef.current = null
              setIsDragging(false)
              if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId)
              }
            }}
          >
            <div
              ref={containerRef}
              className="mx-auto min-w-full w-max [&_.file-space-docx-wrapper]:bg-transparent [&_.file-space-docx-wrapper]:p-1 [&_.file-space-docx-wrapper]:shadow-none [&_.file-space-docx]:shadow-[0_18px_40px_rgba(15,23,42,0.1)]"
            />
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border/50 bg-background/92 px-2 py-1.5 shadow-sm backdrop-blur-sm">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => setZoom((current) => clamp(current / 1.2, MIN_ZOOM, MAX_ZOOM))}
            disabled={zoom <= MIN_ZOOM}
            aria-label="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <div className="min-w-14 text-center text-xs font-medium tabular-nums text-muted-foreground">
            {Math.round(zoom * 100)}%
          </div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => setZoom((current) => clamp(current * 1.2, MIN_ZOOM, MAX_ZOOM))}
            disabled={zoom >= MAX_ZOOM}
            aria-label="Zoom in"
          >
            <Plus className="h-4 w-4" />
          </Button>
          <div className="h-5 w-px bg-border/60" />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => {
              setZoom(1)
              setTranslate({ x: 0, y: 0 })
            }}
            disabled={zoom === 1}
            aria-label="Reset document zoom"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
          <div className="h-5 w-px bg-border/60" />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => jumpToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            aria-label="Previous document page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="text-xs text-muted-foreground">Page</div>
          <input
            aria-label="Jump to document page"
            value={pageInput}
            onChange={(event) => setPageInput(event.target.value.replace(/[^\d]/g, ""))}
            onBlur={() => jumpToPage(Number(pageInput || "1"))}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                jumpToPage(Number(pageInput || "1"))
              }
            }}
            className="h-8 w-12 rounded-full border border-border/60 bg-background px-3 text-center text-xs outline-none ring-0"
          />
          <div className="min-w-10 text-xs text-muted-foreground">/ {pageCount}</div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => jumpToPage(currentPage + 1)}
            disabled={currentPage >= pageCount}
            aria-label="Next document page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
