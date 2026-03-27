import { buildArtifactDetailHref, buildArtifactNewHref } from "@/components/admin/artifacts/artifactRoutes"

describe("artifactRoutes", () => {
  it("builds the detail route for an artifact id", () => {
    expect(buildArtifactDetailHref("artifact-123")).toBe("/admin/artifacts/artifact-123")
  })

  it("builds the create route with query params", () => {
    expect(buildArtifactNewHref({
      kind: "tool_impl",
      language: "javascript",
      draftKey: "draft-1",
    })).toBe("/admin/artifacts/new?kind=tool_impl&language=javascript&draftKey=draft-1")
  })
})
