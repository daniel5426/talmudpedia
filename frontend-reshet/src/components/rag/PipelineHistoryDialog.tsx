"use client"

import React from "react"
import { History } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { PipelineExecutionsTable } from "./PipelineExecutionsTable"
import { VisualPipeline, PipelineJob } from "@/services"

interface PipelineHistoryDialogProps {
  pipeline: VisualPipeline | null
  jobs: PipelineJob[]
  isLoading: boolean
  allPipelines: VisualPipeline[]
  onClose: () => void
}

export function PipelineHistoryDialog({
  pipeline,
  jobs,
  isLoading,
  allPipelines,
  onClose,
}: PipelineHistoryDialogProps) {
  return (
    <Dialog open={!!pipeline} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-7xl w-full max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="h-5 w-5" />
            Execution History: {pipeline?.name}
          </DialogTitle>
          <DialogDescription>
            Past executions for this pipeline across all versions.
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-auto py-4">
          <PipelineExecutionsTable
            jobs={jobs}
            pipelines={allPipelines}
            isLoading={isLoading}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
