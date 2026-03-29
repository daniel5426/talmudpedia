import { buildRenamedFilePath } from "@/components/admin/artifacts/artifactWorkspaceUtils"

describe("artifactWorkspaceUtils", () => {
  it("renames only the file segment and preserves parent directories", () => {
    expect(buildRenamedFilePath("src/helpers/main.py", "runner.py")).toBe("src/helpers/runner.py")
  })

  it("rejects empty file names", () => {
    expect(() => buildRenamedFilePath("main.py", "   ")).toThrow("File name cannot be empty")
  })

  it("rejects path separators in renamed file names", () => {
    expect(() => buildRenamedFilePath("main.py", "src/runner.py")).toThrow("File name cannot contain '/'")
  })
})
