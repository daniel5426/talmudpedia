import { GlobeIcon } from "lucide-react";
import { startTransition, useLayoutEffect, useState } from "react";
import {
    PromptInput,
    PromptInputTextarea,
    PromptInputBody,
    PromptInputFooter,
    PromptInputTools,
    PromptInputActionMenu,
    PromptInputActionMenuTrigger,
    PromptInputActionMenuContent,
    PromptInputActionAddAttachments,
    PromptInputButton,
    PromptInputProvider,
    PromptInputAttachments,
    PromptInputAttachment as NewPromptInputAttachment,
    PromptInputSubmit,
    PromptInputSpeechButton,
  } from "@/components/ai-elements/prompt-input";
import { Headphones } from "lucide-react";
import { useDirection } from "./direction-provider";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { SelectedTextCard } from "@/components/ui/selected-text-card";
import { nanoid } from "nanoid";
import { cn } from "@/lib/utils";
import { AudioWaveform } from "@/components/ui/audio-waveform";


interface BotImputAreaProps {
  className?: string;
  textareaRef: any;
  handleSubmit: any;
  isLoading?: boolean;
  onStop?: () => void;
  isVoiceModeActive?: boolean;
  onToggleVoiceMode?: () => void;
  analyser?: AnalyserNode | null;
}

export function BotImputArea({ 
  className = "", 
  textareaRef, 
  handleSubmit, 
  isLoading = false,
  onStop,
  isVoiceModeActive,
  onToggleVoiceMode,
  analyser
}: BotImputAreaProps) {
  const { direction } = useDirection();
  const selectedText = useLayoutStore((state) => state.selectedText);
  const setSelectedText = useLayoutStore((state) => state.setSelectedText);
  const [isMounted, setIsMounted] = useState(false);
  
  useLayoutEffect(() => {
    startTransition(() => {
      setIsMounted(true);
    });
  }, []);
  
  const handleFormSubmit = (message: any) => {
    if (isLoading && onStop) {
      onStop();
    } else {
      if (selectedText) {
        const textBlob = new Blob([selectedText.text], { type: "text/plain" });
        const textFile = {
          id: nanoid(),
          type: "file" as const,
          url: URL.createObjectURL(textBlob),
          mediaType: "text/plain",
          filename: `Selection from ${selectedText.sourceRef || "Source"}`,
        };
        
        message.files = [...(message.files || []), textFile];
        
        setSelectedText(null);
      }
      
      handleSubmit(message);
    }
  };

  if (!isMounted) {
    return (
      <></>
    );
  }

   return (
    <div className="animate-in w-full fade-in slide-in-from-bottom-4 duration-500">
      <PromptInputProvider>
        <PromptInputAttachments>
          {(attachment) => <NewPromptInputAttachment data={attachment} />}
        </PromptInputAttachments>
        
        {selectedText && (
          <div className={cn("px-3 pb-2 w-fit", direction === "rtl" ? "ml-auto" : "mr-auto")}>
            <SelectedTextCard 
              text={selectedText.text} 
              sourceRef={selectedText.sourceRef} 
              onRemove={() => setSelectedText(null)} 
            />
          </div>
        )}

      <PromptInput
        dir={direction}
        onSubmit={handleFormSubmit}
        className={`relative ${className} bg-primary-soft shadow-sm border-none rounded-md`}
      >
        <PromptInputBody>
          {isVoiceModeActive ? (
              <div className="flex flex-col gap-2 w-full px-4 py-3">
                <div
                  className={cn(
                    "inline-flex items-center gap-2 text-xs font-medium",
                    direction === "rtl" ? "self-end" : "self-start"
                  )}
                  role="status"
                  aria-live="polite"
                >
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500/40 animate-ping" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  </span>
                  <span className="text-muted-foreground">Voice mode active</span>
                  <span className="text-muted-foreground/60">•</span>
                  <span className="text-muted-foreground/80">
                    Click <span className="font-semibold text-muted-foreground">headphones</span> to stop
                  </span>
                </div>

                <div className="flex items-center justify-center">
                  <AudioWaveform
                    barCount={44}
                    className="text-primary w-full max-w-md h-9"
                    analyser={analyser}
                  />
                </div>
              </div>
          ) : (
              <PromptInputTextarea
                  ref={textareaRef}
                  className=""
              />
          )}
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputTools className="text-foreground">
            {!isVoiceModeActive && (
                <>
                    <PromptInputActionMenu>
                      <PromptInputActionMenuTrigger />
                      <PromptInputActionMenuContent>
                        <PromptInputActionAddAttachments />
                      </PromptInputActionMenuContent>
                    </PromptInputActionMenu>
                    <PromptInputSpeechButton textareaRef={textareaRef} />
                    <PromptInputButton >
                      <GlobeIcon size={16} />
                    </PromptInputButton>
                </>
            )}
            <PromptInputButton
              onClick={onToggleVoiceMode}
              className={cn(
                "relative transition-colors",
                isVoiceModeActive
                  ? "text-red-600 bg-red-500/10 hover:bg-red-500/15 dark:text-red-400 dark:bg-red-500/15 dark:hover:bg-red-500/20"
                  : "text-muted-foreground hover:text-foreground"
              )}
              type="button"
              title={isVoiceModeActive ? "Stop Voice Mode" : "Start Voice Mode"}
              aria-pressed={!!isVoiceModeActive}
            >
              <Headphones size={16} />
            </PromptInputButton>
          </PromptInputTools>
          {!isVoiceModeActive && <PromptInputSubmit status={isLoading ? "streaming" : undefined} />}
        </PromptInputFooter>
      </PromptInput>
    </PromptInputProvider>
    </div>
  );
}