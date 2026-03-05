import { extractPrimaryToolPath, formatToolReadPath } from "@/features/apps-builder/workspace/chat/chat-model";

describe("chat model path parsing", () => {
  it("converts temp uuid workspace paths into workspace-relative read labels", () => {
    const tempWorkspacePath =
      "/private/tmp/talmudpedia-draft-dev/c61cada4-b3d2-41e5-a438-1b1767501674/src/components/BotInputArea.tsx";

    expect(formatToolReadPath(tempWorkspacePath)).toBe("src/components/BotInputArea.tsx");
    expect(extractPrimaryToolPath({ path: tempWorkspacePath })).toBe("src/components/BotInputArea.tsx");
  });

  it("keeps existing workspace marker normalization intact", () => {
    const stagedPath = "/private/tmp/talmudpedia-draft-dev/sandbox/.talmudpedia/stage/run-1/workspace/src/App.tsx";
    expect(formatToolReadPath(stagedPath)).toBe("src/App.tsx");
  });
});
