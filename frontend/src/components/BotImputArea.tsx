import { GlobeIcon } from "lucide-react";
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
import { FileUIPart } from "ai";
import { useDirection } from "./direction-provider";


export function BotImputArea({ className = "", textareaRef, handleSubmit }: { className?: string, textareaRef: any, handleSubmit: any }) {
  const { direction } = useDirection();
  const isRTL = direction === "rtl";
   return (
    <PromptInputProvider>
    <PromptInput
      dir={direction}
      onSubmit={handleSubmit}
      className={`relative ${className}`}
    >
      <PromptInputAttachments>
        {(attachment) => <NewPromptInputAttachment data={attachment} />}
      </PromptInputAttachments>
      <PromptInputBody>
        <PromptInputTextarea
          ref={textareaRef}
          className=""
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <PromptInputActionMenu>
            <PromptInputActionMenuTrigger />
            <PromptInputActionMenuContent>
              <PromptInputActionAddAttachments />
            </PromptInputActionMenuContent>
          </PromptInputActionMenu>
          <PromptInputSpeechButton textareaRef={textareaRef} />
          <PromptInputButton>
            <GlobeIcon size={16} />
            <span>Search</span>
          </PromptInputButton>
        </PromptInputTools>
        <PromptInputSubmit />
      </PromptInputFooter>
    </PromptInput>
  </PromptInputProvider>
  );
}