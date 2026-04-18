"use client"

import { useEffect, useRef, useState } from "react"
import Image from "next/image"
import { Minus, Plus, RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"

type FileSpaceImagePreviewProps = {
  src: string
  alt: string
}

type ViewState = {
  zoom: number
  translateX: number
  translateY: number
}

const MIN_ZOOM = 1
const MAX_ZOOM = 6

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

export function FileSpaceImagePreview({ src, alt }: FileSpaceImagePreviewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const dragStateRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    startTranslateX: number
    startTranslateY: number
  } | null>(null)
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [viewState, setViewState] = useState<ViewState>({
    zoom: MIN_ZOOM,
    translateX: 0,
    translateY: 0,
  })

  const baseScale =
    containerSize.width > 0 && containerSize.height > 0 && imageSize.width > 0 && imageSize.height > 0
      ? Math.min(containerSize.width / imageSize.width, containerSize.height / imageSize.height, 1)
      : 1
  const displayScale = baseScale * viewState.zoom

  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof ResizeObserver === "undefined") return

    const observer = new ResizeObserver((entries) => {
      const nextRect = entries[0]?.contentRect
      if (!nextRect) return
      setContainerSize({
        width: nextRect.width,
        height: nextRect.height,
      })
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const updateZoom = (nextZoom: number, anchor?: { clientX: number; clientY: number }) => {
    const boundedZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM)

    setViewState((current) => {
      if (current.zoom === boundedZoom) {
        return current
      }

      if (!anchor || !containerRef.current) {
        return { ...current, zoom: boundedZoom }
      }

      const rect = containerRef.current.getBoundingClientRect()
      const anchorX = anchor.clientX - rect.left - rect.width / 2
      const anchorY = anchor.clientY - rect.top - rect.height / 2
      const currentScale = baseScale * current.zoom
      const nextScale = baseScale * boundedZoom

      if (currentScale <= 0 || nextScale <= 0) {
        return { ...current, zoom: boundedZoom }
      }

      const scaleRatio = nextScale / currentScale

      return {
        zoom: boundedZoom,
        translateX: anchorX - scaleRatio * (anchorX - current.translateX),
        translateY: anchorY - scaleRatio * (anchorY - current.translateY),
      }
    })
  }

  const resetView = () => {
    setViewState({
      zoom: MIN_ZOOM,
      translateX: 0,
      translateY: 0,
    })
  }

  return (
    <div className="relative h-full min-h-[24rem] overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_top,_hsl(var(--muted))_0,_transparent_58%),linear-gradient(180deg,hsl(var(--background)),hsl(var(--muted)/0.55))]">

      <div
        ref={containerRef}
        aria-label="Image preview viewport"
        className={`relative h-full w-full touch-none select-none overflow-hidden ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
        onDoubleClick={resetView}
        onWheel={(event) => {
          event.preventDefault()
          const nextZoom = viewState.zoom * Math.exp(-event.deltaY * 0.0015)
          updateZoom(nextZoom, { clientX: event.clientX, clientY: event.clientY })
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return
          dragStateRef.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            startTranslateX: viewState.translateX,
            startTranslateY: viewState.translateY,
          }
          setIsDragging(true)
          if (event.currentTarget.hasPointerCapture && !event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.setPointerCapture(event.pointerId)
          }
        }}
        onPointerMove={(event) => {
          const dragState = dragStateRef.current
          if (!dragState || dragState.pointerId !== event.pointerId) return

          setViewState((current) => ({
            ...current,
            translateX: dragState.startTranslateX + (event.clientX - dragState.startX),
            translateY: dragState.startTranslateY + (event.clientY - dragState.startY),
          }))
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
        <Image
          src={src}
          alt={alt}
          width={imageSize.width || 1600}
          height={imageSize.height || 1200}
          unoptimized
          draggable={false}
          onLoad={(event) => {
            setImageSize({
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            })
          }}
          className="absolute left-1/2 top-1/2 max-w-none rounded-xl border border-border/60 bg-card"
          style={{
            transform: `translate(calc(-50% + ${viewState.translateX}px), calc(-50% + ${viewState.translateY}px)) scale(${displayScale})`,
            transformOrigin: "center center",
          }}
        />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border/50 bg-background/92 px-2 py-1.5 backdrop-blur-sm">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => updateZoom(viewState.zoom / 1.2)}
            disabled={viewState.zoom <= MIN_ZOOM}
            aria-label="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <div className="min-w-14 text-center text-xs font-medium tabular-nums text-muted-foreground">
            {Math.round(viewState.zoom * 100)}%
          </div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-full"
            onClick={() => updateZoom(viewState.zoom * 1.2)}
            disabled={viewState.zoom >= MAX_ZOOM}
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
            onClick={resetView}
            disabled={viewState.zoom === MIN_ZOOM && viewState.translateX === 0 && viewState.translateY === 0}
            aria-label="Reset image view"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
