"use client"

import { useParams } from "next/navigation"

import { ArtifactEditorScreen } from "@/components/admin/artifacts/ArtifactEditorScreen"

export default function ArtifactDetailPage() {
  const params = useParams()
  const artifactId = params.artifactId as string

  return <ArtifactEditorScreen mode="edit" artifactId={artifactId} />
}
