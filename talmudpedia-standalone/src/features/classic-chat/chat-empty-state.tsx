import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";

import { useIsMobile } from "@/hooks/use-mobile";
import { useLocale } from "./locale-context";
import { BotInputArea } from "./bot-input-area";
import type { ComposerSubmitPayload } from "./types";

type ChatEmptyStateProps = {
  errorMessage?: string | null;
  inputValue: string;
  isResponding: boolean;
  onInputValueChange: (value: string) => void;
  onSubmit: (payload: ComposerSubmitPayload) => void | Promise<void>;
  suggestions: readonly string[];
};

export function ChatEmptyState({
  errorMessage,
  inputValue,
  isResponding,
  onInputValueChange,
  onSubmit,
  suggestions,
}: ChatEmptyStateProps) {
  useLocale();
  const isMobile = useIsMobile();
  const visibleSuggestions = isMobile ? suggestions.slice(0, -3) : suggestions;

  return (
    <div className="flex h-full w-full flex-col items-center justify-center px-4">
      <div className="flex w-full max-w-3xl flex-col items-center text-center pb-28 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex justify-center pb-8">
          <img
            src="/pricoLogo.png"
            alt="Prico AI Logo"
            className="h-16 w-auto object-contain dark:brightness-[1.78] dark:contrast-[0.90] dark:saturate-[0.9] md:h-20"
          />
        </div>

        <BotInputArea
          errorMessage={errorMessage}
          inputValue={inputValue}
          isLoading={isResponding}
          onInputValueChange={onInputValueChange}
          onSubmit={onSubmit}
        />

        <Suggestions className="mt-5 max-w-3xl">
          {visibleSuggestions.map((suggestion) => (
            <Suggestion
              key={suggestion}
              className="h-auto max-w-[18rem] rounded-md px-3 py-1 text-xs transition-colors sm:max-w-none sm:px-5 sm:text-sm"
              onClick={() => onSubmit({ text: suggestion, files: [] })}
              suggestion={suggestion}
            />
          ))}
        </Suggestions>
      </div>
    </div>
  );
}
