import type { Node } from "@xyflow/react"

const FALLBACK_NODE_WIDTH = 200

interface HorizontalCenteringOptions {
  containerWidth: number
  currentViewportX: number
  zoom: number
  nodes: Pick<Node, "position" | "measured">[]
  occludedLeftWidth?: number
  occludedRightWidth?: number
}

export function getCenteredViewportXForPanels({
  containerWidth,
  currentViewportX,
  zoom,
  nodes,
  occludedLeftWidth = 0,
  occludedRightWidth = 0,
}: HorizontalCenteringOptions): number {
  if (nodes.length === 0) {
    return currentViewportX
  }

  const visibleWidth = containerWidth - occludedLeftWidth - occludedRightWidth
  if (visibleWidth <= 0) {
    return currentViewportX
  }

  let minX = Infinity
  let maxX = -Infinity

  nodes.forEach((node) => {
    const nodeWidth = node.measured?.width ?? FALLBACK_NODE_WIDTH
    minX = Math.min(minX, node.position.x)
    maxX = Math.max(maxX, node.position.x + nodeWidth)
  })

  const contentCenterFlowX = (minX + maxX) / 2
  const targetScreenCenterX = occludedLeftWidth + visibleWidth / 2
  const currentScreenCenterX = contentCenterFlowX * zoom + currentViewportX

  return currentViewportX + (targetScreenCenterX - currentScreenCenterX)
}
