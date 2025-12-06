"use client";

import React, { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Paperclip,
  Mic,
  Globe,
  ArrowUp,
  X,
  Loader2,
  FileText,
  Image as ImageIcon,
  MoreHorizontal,
} from "lucide-react";
import { useDirection } from "./direction-provider";
import { nanoid } from "nanoid";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { AudioWaveform } from "@/components/ui/audio-waveform";

const SOURCE_OPTIONS = ["גמרא", "שולחן ערוך", "תנך", "אחרונים", "ראשונים", "משנה"];

interface FileAttachment {
  id: string;
  file: File;
  previewUrl?: string;
  type: "image" | "file";
}

interface DocumentSearchInputAreaProps {
  className?: string;
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
  handleSubmit: (data: { text: string; files: any[] }) => void;
}

export function DocumentSearchInputArea({ 
  className = "", 
  textareaRef: externalTextareaRef = undefined as any, 
  handleSubmit 
}: DocumentSearchInputAreaProps) {
  const { direction } = useDirection();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<FileAttachment[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [isProcessingSpeech, setIsProcessingSpeech] = useState(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [sourceQuery, setSourceQuery] = useState("");
  const [isSourceMenuOpen, setIsSourceMenuOpen] = useState(false);
  
  const internalTextareaRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = externalTextareaRef || internalTextareaRef;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // --- File Handling ---

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addFiles(Array.from(e.target.files));
    }
    // Reset input so same file can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const addFiles = (newFiles: File[]) => {
    const attachments: FileAttachment[] = newFiles.map((file) => ({
      id: nanoid(),
      file,
      previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
      type: file.type.startsWith("image/") ? "image" : "file",
    }));
    setFiles((prev) => [...prev, ...attachments]);
  };

  const removeFile = (id: string) => {
    setFiles((prev) => {
      const fileToRemove = prev.find((f) => f.id === id);
      if (fileToRemove?.previewUrl) {
        URL.revokeObjectURL(fileToRemove.previewUrl);
      }
      return prev.filter((f) => f.id !== id);
    });
  };

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      files.forEach((file) => {
        if (file.previewUrl) URL.revokeObjectURL(file.previewUrl);
      });
    };
  }, [files]);

  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // --- Speech to Text ---

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Set up Audio Context for visualization
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 256;
      source.connect(analyserNode);
      setAnalyser(analyserNode);

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        setIsProcessingSpeech(true);
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", audioBlob, "recording.webm");

        try {
          const response = await fetch("/api/py/stt/transcribe", {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            throw new Error("Transcription failed");
          }

          const data = await response.json();
          const transcript = data.text;

          if (transcript) {
            setText((prev) => prev + (prev ? " " : "") + transcript);
          }
        } catch (error) {
          console.error("Transcription error:", error);
        } finally {
          setIsProcessingSpeech(false);
          setIsListening(false);
          
          // Cleanup audio context and stream
          if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
          }
          if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
          }
          setAnalyser(null);
        }
      };

      mediaRecorder.start();
      setIsListening(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      setIsListening(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  };

  const toggleListening = () => {
    if (isListening) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleSourceSelect = (source: string) => {
    setSelectedSources((prev) => {
      if (prev.includes(source)) return prev;
      return [...prev, source];
    });
    setIsSourceMenuOpen(false);
    setSourceQuery("");
  };

  const removeSourceChip = (source: string) => {
    setSelectedSources((prev) => prev.filter((item) => item !== source));
  };

  const filteredSources = SOURCE_OPTIONS.filter((source) =>
    source.toLowerCase().includes(sourceQuery.toLowerCase())
  );
  

  // --- Submission ---

  const onSubmit = () => {
    if (!text.trim() && files.length === 0) return;

    // Convert internal file format to what the parent expects (FileUIPart-like)
    // Note: The parent 'handleSubmit' expects { text: string; files: any[] }
    // We'll pass the raw files or process them as needed. 
    // Based on previous code, it seems to expect objects with url/type/filename.
    // For now, let's pass a simplified structure or the raw files if the parent handles it.
    // Looking at BotImputArea, it passed `files: convertedFiles` where convertedFiles had data URLs.
    // Let's replicate the data URL conversion for compatibility if needed, 
    // OR just pass the raw files if the backend handles FormData.
    // The previous implementation in PromptInput did convert to DataURL. 
    // Let's do that to be safe and consistent with previous behavior.

    const processFiles = async () => {
      const processedFiles = await Promise.all(files.map(async (f) => {
        return {
          id: f.id,
          type: "file", // or 'image' based on mime
          mediaType: f.file.type,
          filename: f.file.name,
          url: await new Promise<string>((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result as string);
            reader.readAsDataURL(f.file);
          })
        };
      }));

      handleSubmit({ text, files: processedFiles });
      setText("");
      setFiles([]);
    };

    processFiles();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className={cn("flex flex-col gap-2 w-full", className)} dir={direction}>
      <input
        type="file"
        multiple
        className="hidden"
        ref={fileInputRef}
        onChange={handleFileSelect}
      />

      {/* Top Block: Attachments + Textarea */}
      <div className="flex flex-col rounded-sm transition-all">
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 p-2">
            {files.map((file) => (
              <div
                key={file.id}
                className="group relative flex items-center gap-2 bg-background border rounded-sm px-2 py-1 text-sm pr-8"
              >
                {file.type === "image" ? (
                  <ImageIcon className="size-4 text-blue-500" />
                ) : (
                  <FileText className="size-4 text-orange-500" />
                )}
                <span className="truncate max-w-[150px]">{file.file.name}</span>
                <button
                  onClick={() => removeFile(file.id)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-col gap-2">
        <div className="flex items-end shadow-sm rounded-md bg-primary-soft relative">
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="תאר את המידע שאתה רוצה למצוא"
            className="min-h-[50px] border-0 focus-visible:ring-0 resize-none p-3"
          />
          {isListening && (
            <div className="absolute inset-0 flex items-center justify-center bg-primary-soft z-10 rounded-md">
              <AudioWaveform barCount={90} analyser={analyser} />
            </div>
          )}
          <Button
            size="icon"
            className="m-3 size-8 shrink-0"
            onClick={onSubmit}
            disabled={!text.trim() && files.length === 0}
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
        </div>
      </div>

      {/* Bottom Block: Tools + Submit */}
      <div dir={direction} className="flex flex-wrap bg-primary-soft rounded-sm shadow-sm text-black items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 rounded-md  p-2">
          <DropdownMenu open={isSourceMenuOpen} onOpenChange={(open) => {
            setIsSourceMenuOpen(open);
            if (!open) setSourceQuery("");
          }}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8">
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align={direction === "rtl" ? "end" : "start"} className="w-fit z-90">
              <div className="p-2">
                <Input
                  placeholder="Search sources"
                  dir={direction}
                  value={sourceQuery}
                  onChange={(e) => setSourceQuery(e.target.value)}
                />
              </div>
              <div className="max-h-48 overflow-auto py-1" dir={direction}>
                {filteredSources.length > 0 ? (
                  filteredSources.map((source) => (
                    <DropdownMenuItem
                      key={source}
                      onSelect={(event) => {
                        event.preventDefault();
                        handleSourceSelect(source);
                      }}
                      className={cn(selectedSources.includes(source) && "text-muted-foreground")}
                    >
                      {source}
                    </DropdownMenuItem>
                  ))
                ) : (
                  <div className="px-2 py-1 text-sm text-muted-foreground">אין מקורות שמתאימים</div>
                )}
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {selectedSources.map((source) => (
            <div
              key={source}
              className="group relative flex items-center gap-2 rounded-md bg-background border px-2 py-1 text-sm pr-7"
            >
              <span>{source}</span>
              <button
                onClick={() => removeSourceChip(source)}
                className="absolute right-1 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-1 rounded-md   p-2">
              <Button onClick={() => fileInputRef.current?.click()} variant="ghost" size="icon" className="size-8 hover:primary">
                <Paperclip className="size-4" />
              </Button>

          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "size-8  transition-all duration-200",
              isListening && "animate-pulse bg-red-100 text-red-600 hover:bg-red-200 hover:text-red-700"
            )}
            onClick={toggleListening}
            disabled={isProcessingSpeech}
          >
            {isProcessingSpeech ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Mic className="size-4" />
            )}
          </Button>

          <Button variant="ghost" size="sm" className="h-8 gap-2 ">
            <Globe className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
