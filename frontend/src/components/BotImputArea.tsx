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
import { useDirection } from "./direction-provider";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { SelectedTextCard } from "@/components/ui/selected-text-card";
import { nanoid } from "nanoid";
import { cn } from "@/lib/utils";


interface BotImputAreaProps {
  className?: string;
  textareaRef: any;
  handleSubmit: any;
  isLoading?: boolean;
  onStop?: () => void;
}

export function BotImputArea({ 
  className = "", 
  textareaRef, 
  handleSubmit, 
  isLoading = false,
  onStop 
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
          <PromptInputTextarea
            ref={textareaRef}
            className=""
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputTools className="text-black">
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
          </PromptInputTools>
          <PromptInputSubmit status={isLoading ? "streaming" : undefined} />
        </PromptInputFooter>
      </PromptInput>
    </PromptInputProvider>
    </div>
  );
}