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
import { useDirection } from "./direction-provider";


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
  
  const handleFormSubmit = (message: any) => {
    // If currently streaming, stop the request instead of submitting
    if (isLoading && onStop) {
      onStop();
    } else {
      handleSubmit(message);
    }
  };

   return (
    <PromptInputProvider>
    <PromptInput
      dir={direction}
      onSubmit={handleFormSubmit}
      className={`relative ${className} bg-primary-soft shadow-sm border-none rounded-md`}
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
  );
}