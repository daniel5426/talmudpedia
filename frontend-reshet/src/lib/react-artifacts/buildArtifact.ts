import type { ReactArtifact } from "./types";
import { parseReactArtifact } from "./parseReactArtifact";

export const buildReactArtifactFromMessage = (
  content: string,
  sourceMessageId: string
): ReactArtifact | null => {
  const parsed = parseReactArtifact(content);
  if (!parsed) return null;

  return {
    id: `artifact-${sourceMessageId}`,
    title: parsed.title || "React Artifact",
    code: parsed.code,
    language: parsed.language,
    sourceMessageId,
    updatedAt: new Date().toISOString(),
  };
};
