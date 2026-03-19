import { Paperclip, Square } from "lucide-react";

import {
  type PromptInputMessage,
  PromptInput,
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { cn } from "@/lib/utils";
import { useLocale } from "./locale-context";
import type { ComposerSubmitPayload } from "./types";

type BotInputAreaProps = {
  className?: string;
  compact?: boolean;
  errorMessage?: string | null;
  inputValue: string;
  isLoading: boolean;
  onInputValueChange: (value: string) => void;
  onSubmit: (payload: ComposerSubmitPayload) => void | Promise<void>;
};

export function BotInputArea({
  className,
  compact = false,
  errorMessage,
  inputValue,
  isLoading,
  onInputValueChange,
  onSubmit,
}: BotInputAreaProps) {
  const { isRtl, locale } = useLocale();

  return (
    <div className={cn("w-full", compact ? "max-w-3xl" : "max-w-3xl", className)}>
      <PromptInputProvider initialInput={inputValue}>
        <PromptInput
          className={cn(
            "relative bg-muted/50 border-[0.4px] border-border/60 rounded-md",
            "[&_[data-slot=input-group]]:has-[[data-slot=input-group-control]:focus-visible]:ring-0",
            "[&_[data-slot=input-group]]:has-[[data-slot=input-group-control]:focus-visible]:border-input"
          )}
          onSubmit={(message: PromptInputMessage) =>
            onSubmit({
              text: message.text,
              files: message.files.map((file) => ({
                filename: file.filename || "attachment",
                mediaType: file.mediaType,
                url: file.url,
              })),
            })
          }
        >
          <PromptInputBody>
            <PromptInputTextarea
              className="min-h-[48px] bg-transparent text-[0.95rem] md:text-[0.95rem]"
              onChange={(event) => onInputValueChange(event.target.value)}
              placeholder={locale === "he" ? "כתוב הודעה..." : "Message..."}
              value={inputValue}
            />
          </PromptInputBody>
          <PromptInputFooter className="pb-2">
            <PromptInputTools className="text-muted-foreground">
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger />
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>

              <PromptInputButton
                type="button"
                title={locale === "he" ? "הוסף הקשר" : "Add context"}
              >
                <Paperclip className="size-4" />
              </PromptInputButton>
            </PromptInputTools>

            <PromptInputSubmit status={isLoading ? "streaming" : undefined}>
              {isLoading ? <Square className="size-4" /> : null}
            </PromptInputSubmit>
          </PromptInputFooter>
        </PromptInput>
      </PromptInputProvider>
      {errorMessage ? (
        <p className={cn("mt-2 px-1 text-xs text-destructive", isRtl ? "text-right" : "text-left")}>
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
