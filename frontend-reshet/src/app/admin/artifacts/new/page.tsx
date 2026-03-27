"use client"

import { useSearchParams } from "next/navigation"

import { ArtifactEditorScreen } from "@/components/admin/artifacts/ArtifactEditorScreen"
import type { ArtifactKind, ArtifactLanguage } from "@/services/artifacts"

export default function NewArtifactPage() {
  const searchParams = useSearchParams()
  const kindParam = searchParams.get("kind") as ArtifactKind | null
  const languageParam = searchParams.get("language") as ArtifactLanguage | null
  const draftKeyParam = searchParams.get("draftKey")

  const kind: ArtifactKind = kindParam && ["agent_node", "rag_operator", "tool_impl"].includes(kindParam)
    ? kindParam
    : "agent_node"
  const language: ArtifactLanguage = languageParam === "javascript" ? "javascript" : "python"

  return (
    <ArtifactEditorScreen
      mode="create"
      initialKind={kind}
      initialLanguage={language}
      initialDraftKey={draftKeyParam || undefined}
    />
  )
}
