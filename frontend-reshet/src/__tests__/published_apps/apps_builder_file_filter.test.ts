import {
  filterAppsBuilderFiles,
  isAppsBuilderBlockedFilePath,
} from "@/services/apps-builder-file-filter";

describe("apps-builder-file-filter", () => {
  it("blocks generated/runtime paths", () => {
    expect(isAppsBuilderBlockedFilePath(".cache/tmp.json")).toBe(true);
    expect(isAppsBuilderBlockedFilePath("node_modules/react/index.js")).toBe(true);
    expect(isAppsBuilderBlockedFilePath(".talmudpedia/stage/shared/workspace/src/App.tsx")).toBe(true);
  });

  it("keeps source files", () => {
    expect(isAppsBuilderBlockedFilePath("src/App.tsx")).toBe(false);
    expect(isAppsBuilderBlockedFilePath("package.json")).toBe(false);
  });

  it("filters blocked files from payloads", () => {
    expect(
      filterAppsBuilderFiles({
        "src/App.tsx": "export default 1",
        ".cache/state.json": "{}",
        "node_modules/react/index.js": "ignored",
      }),
    ).toEqual({
      "src/App.tsx": "export default 1",
    });
  });
});
