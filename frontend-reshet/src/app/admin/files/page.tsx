"use client"

import { useCallback, useEffect, useState } from "react"

import { FileSpaceEditorHeader } from "@/components/admin/files/FileSpaceEditorHeader"
import { FileSpaceListView } from "@/components/admin/files/FileSpaceListView"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { fileSpacesService, type FileSpace } from "@/services"

export default function FilesPage() {
  const [spaces, setSpaces] = useState<FileSpace[]>([])
  const [loading, setLoading] = useState(true)
  const [bulkAction, setBulkAction] = useState<"delete" | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const loadSpaces = useCallback(async () => {
    try {
      setLoading(true)
      const response = await fileSpacesService.list()
      setSpaces(response.items)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSpaces()
  }, [loadSpaces])

  async function handleCreate() {
    if (!name.trim()) return
    try {
      setSubmitting(true)
      await fileSpacesService.create({ name: name.trim(), description: description.trim() || null })
      setName("")
      setDescription("")
      setOpen(false)
      await loadSpaces()
    } catch (err) {
      console.error(err)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteSpace = useCallback(
    async (space: FileSpace) => {
      if (!window.confirm(`Archive "${space.name}"?`)) return
      try {
        await fileSpacesService.archive(space.id)
        await loadSpaces()
      } catch (err) {
        console.error(err)
      }
    },
    [loadSpaces],
  )

  const handleBulkDelete = useCallback(
    async (selectedSpaces: FileSpace[]) => {
      if (selectedSpaces.length === 0) return
      if (
        !window.confirm(
          `Archive ${selectedSpaces.length} selected file space${selectedSpaces.length === 1 ? "" : "s"}?`,
        )
      )
        return
      setBulkAction("delete")
      try {
        for (const space of selectedSpaces) {
          await fileSpacesService.archive(space.id)
        }
        await loadSpaces()
      } catch (err) {
        console.error(err)
      } finally {
        setBulkAction(null)
      }
    },
    [loadSpaces],
  )

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
      <FileSpaceEditorHeader
        viewMode="list"
        controlsDisabled={loading}
        onRefresh={() => {
          void loadSpaces()
        }}
        onCreateSpace={() => setOpen(true)}
      />
      <div className="flex-1 overflow-auto px-4 pb-4 pt-3" data-admin-page-scroll>
        <FileSpaceListView
          loading={loading}
          spaces={spaces}
          bulkAction={bulkAction}
          onDeleteSpace={(space) => {
            void handleDeleteSpace(space)
          }}
          onBulkDeleteSpaces={(selectedSpaces) => handleBulkDelete(selectedSpaces)}
        />
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create File Space</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Research Workspace"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Textarea
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={submitting || !name.trim()}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
