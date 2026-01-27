"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTenant } from "@/contexts/TenantContext"
import { ragAdminService, VisualPipeline } from "@/services"
import { CustomBreadcrumb } from "@/components/ui/custom-breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Plus,
  RefreshCw,
  Trash2,
  Edit,
  CheckCircle2,
} from "lucide-react"

export default function PipelinesPage() {
  const { currentTenant } = useTenant()
  const router = useRouter()

  const [loading, setLoading] = useState(true)
  const [pipelines, setPipelines] = useState<VisualPipeline[]>([])

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const pipelinesRes = await ragAdminService.listVisualPipelines(currentTenant?.slug)
      setPipelines(pipelinesRes.pipelines)
    } catch (error) {
      console.error("Failed to fetch pipelines data", error)
    } finally {
      setLoading(false)
    }
  }, [currentTenant?.slug])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleDelete = async (pipelineId: string) => {
    if (!confirm("Are you sure you want to delete this pipeline?")) return
    try {
      await ragAdminService.deleteVisualPipeline(pipelineId, currentTenant?.slug)
      fetchData()
    } catch (error) {
      console.error("Failed to delete pipeline", error)
    }
  }

  return (
    <div className="flex flex-col h-full w-full">
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background z-30 shrink-0">
        <div className="flex items-center gap-3">
          <CustomBreadcrumb
            items={[
              { label: "RAG Management", href: "/admin/rag" },
              { label: "Pipelines", active: true },
            ]}
          />
        </div>
      </header>
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-[400px] w-full" />
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-lg font-semibold">Visual Pipelines</h2>
                <p className="text-sm text-muted-foreground">
                  Drag-and-drop RAG pipeline configurations
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={fetchData}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh
                </Button>
                <Button size="sm" onClick={() => router.push("/admin/pipelines/new")}>
                  <Plus className="h-4 w-4 mr-2" />
                  New Pipeline
                </Button>
              </div>
            </div>

            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pipelines.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                        No pipelines found. Create one to get started.
                      </TableCell>
                    </TableRow>
                  ) : (
                    pipelines.map((pipeline) => (
                      <TableRow key={pipeline.id}>
                        <TableCell className="font-medium">{pipeline.name}</TableCell>
                        <TableCell className="text-muted-foreground max-w-[200px] truncate">
                          {pipeline.description || "-"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">v{pipeline.version}</Badge>
                        </TableCell>
                        <TableCell>
                          {pipeline.is_published ? (
                            <Badge className="bg-green-500/10 text-green-600 border-green-500/20">
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                              Published
                            </Badge>
                          ) : (
                            <Badge variant="secondary">
                              <Edit className="h-3 w-3 mr-1" />
                              Draft
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {new Date(pipeline.updated_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => router.push(`/admin/pipelines/${pipeline.id}`)}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDelete(pipeline.id)}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
