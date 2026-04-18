"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Document, Page, pdfjs } from "react-pdf"

import { Button } from "@/components/ui/button"

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

type FileSpacePdfPreviewProps = {
  file: Blob
}

function clampPage(page: number, total: number) {
  return Math.min(Math.max(page, 1), Math.max(total, 1))
}

export function FileSpacePdfPreview({ file }: FileSpacePdfPreviewProps) {
  const [numPages, setNumPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageInput, setPageInput] = useState("1")
  const [containerWidth, setContainerWidth] = useState(0)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const node = shellRef.current
    if (!node || typeof ResizeObserver === "undefined") return

    const observer = new ResizeObserver((entries) => {
      const nextWidth = entries[0]?.contentRect.width ?? 0
      setContainerWidth(nextWidth)
    })

    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setCurrentPage(1)
    setPageInput("1")
  }, [file])

  useEffect(() => {
    setPageInput(String(currentPage))
  }, [currentPage])

  const pageWidth = useMemo(() => {
    if (!containerWidth) return 1100
    return Math.max(280, Math.floor(containerWidth) - 32)
  }, [containerWidth])

  const jumpToPage = (requestedPage: number) => {
    const nextPage = clampPage(requestedPage, numPages)
    const container = scrollRef.current
    const target = container?.querySelector<HTMLElement>(`[data-page-number="${nextPage}"]`)
    if (container && target) {
      container.scrollTo({ top: target.offsetTop - 8, behavior: "smooth" })
    }
    setCurrentPage(nextPage)
    setPageInput(String(nextPage))
  }

  return (
    <div
      ref={shellRef}
      className="relative h-full min-h-[24rem] overflow-hidden rounded-2xl border border-border/40 bg-[linear-gradient(180deg,hsl(var(--background)),hsl(var(--muted)/0.1))] shadow-[inset_0_1px_0_hsl(var(--background)),0_1px_2px_rgba(15,23,42,0.04)]"
    >
      <div
        ref={scrollRef}
        aria-label="PDF preview"
        className="h-full overflow-auto overscroll-contain px-1 pb-24 pt-2"
        onScroll={(event) => {
          const container = event.currentTarget
          const pageElements = Array.from(container.querySelectorAll<HTMLElement>("[data-page-number]"))
          const threshold = container.scrollTop + 24
          const nextCurrentPage =
            pageElements.reduce((page, element) => {
              const pageNumber = Number(element.dataset.pageNumber ?? "1")
              return element.offsetTop <= threshold ? pageNumber : page
            }, 1) || 1
          if (nextCurrentPage !== currentPage) {
            setCurrentPage(nextCurrentPage)
          }
        }}
      >
        <Document
          file={file}
          onLoadSuccess={({ numPages: nextNumPages }) => {
            setNumPages(nextNumPages)
            setCurrentPage(1)
            setPageInput("1")
          }}
        >
          <div className="space-y-4">
            {Array.from({ length: numPages }, (_, index) => (
              <div
                key={index + 1}
                data-page-number={index + 1}
                className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm"
              >
                <Page
                  pageNumber={index + 1}
                  width={pageWidth}
                  renderAnnotationLayer={false}
                  renderTextLayer={false}
                />
              </div>
            ))}
          </div>
        </Document>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border/50 bg-background/92 px-2 py-1.5 shadow-sm backdrop-blur-sm">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => jumpToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="text-xs text-muted-foreground">Page</div>
          <input
            aria-label="Jump to PDF page"
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
          <div className="min-w-10 text-xs text-muted-foreground">/ {Math.max(numPages, 1)}</div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => jumpToPage(currentPage + 1)}
            disabled={currentPage >= numPages}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
