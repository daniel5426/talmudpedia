"use client";

import { useCallback, useRef, useState } from "react";
import { ImagePlus, Link, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

type LogoPickerDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentUrl: string;
  onSave: (url: string) => void;
};

export function LogoPickerDialog({
  open,
  onOpenChange,
  currentUrl,
  onSave,
}: LogoPickerDialogProps) {
  const [tab, setTab] = useState<string>("url");
  const [urlInput, setUrlInput] = useState(currentUrl);
  const [previewUrl, setPreviewUrl] = useState(currentUrl);
  const [isDragging, setIsDragging] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (next) {
        setUrlInput(currentUrl);
        setPreviewUrl(currentUrl);
        setPreviewError(false);
        setTab("url");
      }
      onOpenChange(next);
    },
    [currentUrl, onOpenChange],
  );

  const handleFileSelect = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      setPreviewUrl(result);
      setUrlInput(result);
      setPreviewError(false);
      setTab("url");
    };
    reader.readAsDataURL(file);
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setIsDragging(false);
      const file = event.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleUrlCommit = useCallback(() => {
    const trimmed = urlInput.trim();
    if (trimmed) {
      setPreviewUrl(trimmed);
      setPreviewError(false);
    }
  }, [urlInput]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>App Logo</DialogTitle>
          <DialogDescription>Upload an image or paste a URL for your app logo.</DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="url" className="flex-1 gap-1.5">
              <Link className="h-3.5 w-3.5" />
              URL
            </TabsTrigger>
            <TabsTrigger value="upload" className="flex-1 gap-1.5">
              <Upload className="h-3.5 w-3.5" />
              Upload
            </TabsTrigger>
          </TabsList>

          <TabsContent value="url" className="space-y-4 pt-2">
            <div className="flex gap-2">
              <Input
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onBlur={handleUrlCommit}
                onKeyDown={(e) => e.key === "Enter" && handleUrlCommit()}
                placeholder="https://example.com/logo.png"
                className="flex-1"
              />
            </div>
            <div className="flex items-center justify-center rounded-lg border border-dashed border-border/60 bg-muted/30 p-6">
              {previewUrl && !previewError ? (
                <img
                  src={previewUrl}
                  alt="Logo preview"
                  className="h-24 w-24 rounded-md object-cover shadow-sm"
                  onError={() => setPreviewError(true)}
                />
              ) : (
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                  <ImagePlus className="h-10 w-10 opacity-40" />
                  <span className="text-xs">{previewError ? "Failed to load image" : "Preview will appear here"}</span>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="upload" className="pt-2">
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 transition-colors",
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-border/60 bg-muted/30 hover:border-primary/40 hover:bg-muted/50",
              )}
            >
              <div className={cn(
                "flex h-12 w-12 items-center justify-center rounded-full transition-colors",
                isDragging ? "bg-primary/10" : "bg-muted",
              )}>
                <Upload className={cn("h-5 w-5", isDragging ? "text-primary" : "text-muted-foreground")} />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium">
                  {isDragging ? "Drop your image here" : "Drag & drop an image"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">or click to browse</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileSelect(file);
                }}
              />
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSave(previewUrl);
              handleOpenChange(false);
            }}
            disabled={!previewUrl || previewError}
          >
            Save Logo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
