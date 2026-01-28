"use client"

import { useRef, useState } from "react"
import { Loader2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface FileUploadInputProps {
  value?: string
  accept?: string
  disabled?: boolean
  onChange: (value: string) => void
  onUpload: (file: File) => Promise<string>
}

export function FileUploadInput({
  value,
  accept,
  disabled,
  onChange,
  onUpload,
}: FileUploadInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)

  const handleSelect = () => {
    if (disabled || isUploading) return
    inputRef.current?.click()
  }

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setIsUploading(true)
    try {
      const path = await onUpload(file)
      onChange(path)
    } finally {
      setIsUploading(false)
      if (inputRef.current) {
        inputRef.current.value = ""
      }
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Input
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Upload a file or enter a path"
        disabled={disabled || isUploading}
      />
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={handleFileChange}
      />
      <Button
        type="button"
        variant="outline"
        onClick={handleSelect}
        disabled={disabled || isUploading}
        className="shrink-0"
      >
        {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
      </Button>
    </div>
  )
}
