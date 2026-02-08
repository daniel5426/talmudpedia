export type ReactArtifact = {
  id: string;
  title: string;
  code: string;
  language: "tsx" | "jsx" | "react";
  sourceMessageId: string;
  updatedAt: string;
};

export type ReactArtifactCandidate = {
  code: string;
  language: "tsx" | "jsx" | "react";
  title?: string;
};
