"use client"

import { Bot, Database, Edit, Loader2, Package, Trash2, Upload, Wrench } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Artifact, ArtifactKind } from "@/services/artifacts"
import { kindLabel } from "@/components/admin/artifacts/artifactPageUtils"

type ArtifactListViewProps = {
  artifacts: Artifact[]
  publishingId: string | null
  onEditArtifact: (artifact: Artifact) => void
  onDeleteArtifact: (artifact: Artifact) => void
  onPublishArtifact: (artifact: Artifact) => void
}

function kindIcon(kind: ArtifactKind) {
  if (kind === "agent_node") return Bot
  if (kind === "rag_operator") return Database
  return Wrench
}

export function ArtifactListView({
  artifacts,
  publishingId,
  onEditArtifact,
  onDeleteArtifact,
  onPublishArtifact,
}: ArtifactListViewProps) {
  return (
    <div className="m-4 space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Unified artifact runtime</h2>
        <p className="text-sm text-muted-foreground">One execution substrate with explicit domain kinds.</p>
      </div>
      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Artifact</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Version</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {artifacts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-12 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                      <Package className="h-6 w-6" />
                    </div>
                    <span>No artifacts found.</span>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              artifacts.map((artifact) => {
                const Icon = kindIcon(artifact.kind)
                return (
                  <TableRow key={artifact.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-muted p-2">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="flex flex-col">
                          <span>{artifact.display_name}</span>
                          <span className="text-xs text-muted-foreground">{kindLabel(artifact.kind)}</span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{kindLabel(artifact.kind)}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={artifact.owner_type === "system" ? "secondary" : "outline"}>{artifact.owner_type}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{artifact.version}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {artifact.type === "draft" && artifact.owner_type === "tenant" ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Publish"
                            onClick={() => onPublishArtifact(artifact)}
                            disabled={publishingId === artifact.id}
                          >
                            {publishingId === artifact.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                          </Button>
                        ) : null}
                        <Button variant="ghost" size="icon" onClick={() => onEditArtifact(artifact)}>
                          <Edit className="h-4 w-4" />
                        </Button>
                        {artifact.owner_type === "tenant" ? (
                          <Button variant="ghost" size="icon" onClick={() => onDeleteArtifact(artifact)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
