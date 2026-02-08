import type { ReactArtifactCandidate } from "./types";

const FENCE_PATTERN = /```([^\n]*)\n([\s\S]*?)```/g;
const SUPPORTED_LANGS = new Set(["tsx", "jsx", "react"]);

const inferTitle = (code: string) => {
  const exportDefaultMatch = code.match(/export\s+default\s+function\s+([A-Za-z0-9_]+)/);
  if (exportDefaultMatch?.[1]) {
    return exportDefaultMatch[1];
  }
  const functionMatch = code.match(/function\s+([A-Za-z0-9_]+)\s*\(/);
  if (functionMatch?.[1]) {
    return functionMatch[1];
  }
  return "React Artifact";
};

export const parseReactArtifact = (content: string): ReactArtifactCandidate | null => {
  if (!content) return null;
  FENCE_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null = null;

  while ((match = FENCE_PATTERN.exec(content)) !== null) {
    const info = (match[1] || "").trim();
    const language = info.split(/\s+/)[0]?.toLowerCase();
    if (!language || !SUPPORTED_LANGS.has(language)) continue;

    const code = (match[2] || "").trim();
    if (!code) return null;

    return {
      code,
      language: language as ReactArtifactCandidate["language"],
      title: inferTitle(code),
    };
  }

  return null;
};
