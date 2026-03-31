import { ImageIcon, Music2, Paperclip, Settings2 } from "lucide-react";
import { startTransition, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { FileUIPart } from "ai";

import {
  PromptInput,
  PromptInputTextarea,
  PromptInputBody,
  PromptInputFooter,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputButton,
  PromptInputProvider,
  PromptInputAttachments,
  PromptInputAttachment as NewPromptInputAttachment,
  PromptInputSubmit,
  PromptInputSpeechButton,
  usePromptInputAttachments,
} from "@/components/ai-elements/prompt-input";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useDirection } from "./direction-provider";
import { useLayoutStore } from "@/lib/store/useLayoutStore";
import { SelectedTextCard } from "@/components/ui/selected-text-card";
import { nanoid } from "nanoid";
import { cn } from "@/lib/utils";
import { AudioWaveform } from "@/components/ui/audio-waveform";
import type { AgentGraphDefinition } from "@/services/agent";
import { WorkflowStateSettingsDialog } from "@/components/WorkflowStateSettingsDialog";

type WorkflowInput = NonNullable<AgentGraphDefinition["workflow_contract"]>["inputs"][number]
type StateVariable = NonNullable<AgentGraphDefinition["state_contract"]>["variables"][number]

interface BotInputAreaProps {
  className?: string;
  textareaRef: any;
  handleSubmit: (message: { text: string; files: FileUIPart[]; state?: Record<string, unknown> }) => Promise<void> | void;
  isLoading?: boolean;
  onStop?: () => void;
  isVoiceModeActive?: boolean;
  onToggleVoiceMode?: () => void;
  analyser?: AnalyserNode | null;
  animate?: boolean;
  workflowInputs?: WorkflowInput[];
  stateVariables?: StateVariable[];
}

function modalityEnabled(inputs: WorkflowInput[] | undefined, key: string) {
  const item = (inputs || []).find((entry) => String(entry.key) === key)
  return item ? item.enabled !== false : true
}

function UploadMenuItem({
  label,
  accept,
  icon,
}: {
  label: string
  accept?: string
  icon: ReactNode
}) {
  const attachments = usePromptInputAttachments()
  const inputRef = useRef<HTMLInputElement | null>(null)

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={(event) => {
          const files = event.target.files
          if (files && files.length > 0) {
            attachments.add(files)
          }
          event.currentTarget.value = ""
        }}
      />
      <DropdownMenuItem
        onSelect={(event) => {
          event.preventDefault()
          inputRef.current?.click()
        }}
      >
        <span className="mr-2 inline-flex size-4 items-center justify-center">{icon}</span>
        {label}
      </DropdownMenuItem>
    </>
  )
}

export function BotInputArea({
  className = "",
  textareaRef,
  handleSubmit,
  isLoading = false,
  onStop,
  isVoiceModeActive,
  analyser,
  animate = true,
  workflowInputs,
  stateVariables,
}: BotInputAreaProps) {
  const { direction } = useDirection();
  const selectedText = useLayoutStore((state) => state.selectedText);
  const setSelectedText = useLayoutStore((state) => state.setSelectedText);
  const [isMounted, setIsMounted] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingStateValues, setPendingStateValues] = useState<Record<string, unknown>>({});

  const textEnabled = modalityEnabled(workflowInputs, "text")
  const filesEnabled = modalityEnabled(workflowInputs, "files")
  const audioEnabled = modalityEnabled(workflowInputs, "audio")
  const imagesEnabled = modalityEnabled(workflowInputs, "images")
  const hasUploadInputs = filesEnabled || audioEnabled || imagesEnabled
  const hasStateVariables = Array.isArray(stateVariables) && stateVariables.length > 0
  const activeStateValueCount = useMemo(() => Object.keys(pendingStateValues).length, [pendingStateValues])

  useLayoutEffect(() => {
    startTransition(() => {
      setIsMounted(true);
    });
  }, []);

  const handleFormSubmit = (message: { text: string; files: FileUIPart[] }) => {
    if (isLoading && onStop) {
      onStop();
      return;
    }

    const nextMessage = { ...message, files: [...(message.files || [])] }

    if (selectedText && filesEnabled) {
      const textBlob = new Blob([selectedText.text], { type: "text/plain" });
      const textFile = {
        id: nanoid(),
        type: "file" as const,
        url: URL.createObjectURL(textBlob),
        mediaType: "text/plain",
        filename: `Selection from ${selectedText.sourceRef || "Source"}`,
      };

      nextMessage.files = [...nextMessage.files, textFile];
      setSelectedText(null);
    }

    const result = handleSubmit({
      ...nextMessage,
      state: activeStateValueCount > 0 ? pendingStateValues : undefined,
    });
    setPendingStateValues({});
    if (result instanceof Promise) {
      void result.catch((error) => {
        console.error("Bot input submission failed", error)
      })
    }
  };

  if (!isMounted) {
    return <></>;
  }

  return (
    <div className={cn("w-full", animate && "animate-in fade-in slide-in-from-bottom-4 duration-500")}>
      <PromptInputProvider>
        <PromptInputAttachments>
          {(attachment) => <NewPromptInputAttachment data={attachment} />}
        </PromptInputAttachments>

        {selectedText && filesEnabled && (
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
          className={cn(
            "relative",
            className,
            "bg-primary-soft border-[0.4px] rounded-lg",
            "[&_[data-slot=input-group]]:has-[[data-slot=input-group-control]:focus-visible]:ring-0",
            "[&_[data-slot=input-group]]:has-[[data-slot=input-group-control]:focus-visible]:border-input"
          )}
        >
          <PromptInputBody>
            {textEnabled ? (
              <PromptInputTextarea ref={textareaRef} />
            ) : (
              <div className="px-3 py-2 text-[12px] text-muted-foreground/60">
                Text input is disabled for this workflow.
              </div>
            )}
          </PromptInputBody>
          <PromptInputFooter className="pb-2">
            <PromptInputTools className="text-foreground">
              {hasUploadInputs ? (
                <PromptInputActionMenu>
                  <PromptInputActionMenuTrigger />
                  <PromptInputActionMenuContent>
                    {filesEnabled ? <UploadMenuItem label="Add files" icon={<Paperclip className="size-4" />} /> : null}
                    {imagesEnabled ? <UploadMenuItem label="Add images" accept="image/*" icon={<ImageIcon className="size-4" />} /> : null}
                    {audioEnabled ? <UploadMenuItem label="Add audio" accept="audio/*" icon={<Music2 className="size-4" />} /> : null}
                  </PromptInputActionMenuContent>
                </PromptInputActionMenu>
              ) : null}

              {audioEnabled ? (
                <PromptInputSpeechButton
                  mode="attachment"
                  attachmentFilename="workflow-audio-input.webm"
                />
              ) : null}

              <PromptInputButton
                onClick={() => setSettingsOpen(true)}
                className={cn(
                  "relative transition-colors",
                  activeStateValueCount > 0 ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
                type="button"
                title="Workflow state"
              >
                <Settings2 size={16} />
                {activeStateValueCount > 0 ? (
                  <span className="absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full bg-foreground text-[10px] text-background">
                    {activeStateValueCount}
                  </span>
                ) : null}
              </PromptInputButton>
            </PromptInputTools>

            {isVoiceModeActive ? (
              <div className="flex items-center justify-center flex-1 px-4 min-w-0">
                <AudioWaveform
                  barCount={30}
                  className="text-primary w-full h-8 opacity-80"
                  analyser={analyser}
                />
              </div>
            ) : (
              <PromptInputSubmit status={isLoading ? "streaming" : undefined} />
            )}
          </PromptInputFooter>
        </PromptInput>

        <WorkflowStateSettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          stateVariables={stateVariables || []}
          values={pendingStateValues}
          onChange={setPendingStateValues}
        />
      </PromptInputProvider>
    </div>
  );
}
