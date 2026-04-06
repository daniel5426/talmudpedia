import type { Node } from "@xyflow/react"

import { getCenteredViewportXForPanels } from "@/components/agent-builder/canvas-centering"

const buildNode = (x: number, width = 200): Pick<Node, "position" | "measured"> => ({
  position: { x, y: 0 },
  measured: { width, height: 80 },
})

describe("agent builder canvas centering", () => {
  it("fully centers build mode when no side panel is open", () => {
    expect(
      getCenteredViewportXForPanels({
        containerWidth: 1000,
        currentViewportX: 0,
        zoom: 1,
        nodes: [buildNode(100)],
      })
    ).toBe(300)
  })

  it("pushes build mode farther right when the catalog is open", () => {
    expect(
      getCenteredViewportXForPanels({
        containerWidth: 1000,
        currentViewportX: 0,
        zoom: 1,
        nodes: [buildNode(100)],
        occludedLeftWidth: 256,
      })
    ).toBe(428)
  })

  it("pushes execute mode left to avoid the execution panel", () => {
    expect(
      getCenteredViewportXForPanels({
        containerWidth: 1000,
        currentViewportX: 0,
        zoom: 1,
        nodes: [buildNode(100)],
        occludedRightWidth: 400,
      })
    ).toBe(100)
  })
})
