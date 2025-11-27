import { type RefObject } from "react";
import type { FileUIPart } from "ai";
import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { BotImputArea } from "@/components/BotImputArea";

interface ChatLandingEmptyStateProps {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  handleSubmit: (message: { text: string; files: FileUIPart[] }) => void;
  isLoading: boolean;
  onStop: () => void;
  className?: string;
  title?: string;
  description?: string;
}

export function ChatLandingEmptyState({
  textareaRef,
  handleSubmit,
  isLoading,
  onStop,
  className = "",
  title = "ברוך הבה לקשר",
  description = "המקום שבו אפשר לחפש ולעיין בכל התורה כולה במשפט אחד",
}: ChatLandingEmptyStateProps) {
  return (
    <div className={`relative flex h-full w-full bg-transparent items-center justify-center ${className}`}>
      <div className="relative z-10 flex flex-col items-center justify-center w-full max-w-3xl mx-auto bg-transparent p-4 pb-45">
        <div>
          <div
            className="pb-5 text-white  text-center"
          />
          <h3 className="font-medium text-center text-3xl">{title}</h3>
          {description && (
            <p className="text-white pb-2 text-center text-xl">{description}</p>
          )}
        </div>
        <BotImputArea
          textareaRef={textareaRef}
          handleSubmit={handleSubmit}
          isLoading={isLoading}
          onStop={onStop}
        />
      </div>
    </div>
  );
}

