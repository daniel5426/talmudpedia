import type { ArtifactKind, ArtifactLanguage } from "@/services/artifacts"

export const CREATE_DRAFT_KEY_QUERY_PARAM = "draftKey"
export const ARTIFACT_EDITOR_AUTO_COLLAPSE_APP_SIDEBAR_KEY = "artifact-editor:auto-collapse-app-sidebar"

type ArtifactNewRouteOptions = {
  kind?: ArtifactKind
  language?: ArtifactLanguage
  draftKey?: string
}

export function buildArtifactDetailHref(artifactId: string): string {
  return `/admin/artifacts/${encodeURIComponent(artifactId)}`
}

export function buildArtifactNewHref(options: ArtifactNewRouteOptions = {}): string {
  const params = new URLSearchParams()
  if (options.kind) params.set("kind", options.kind)
  if (options.language) params.set("language", options.language)
  if (options.draftKey) params.set(CREATE_DRAFT_KEY_QUERY_PARAM, options.draftKey)
  const query = params.toString()
  return query ? `/admin/artifacts/new?${query}` : "/admin/artifacts/new"
}
