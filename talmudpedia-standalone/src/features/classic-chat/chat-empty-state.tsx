import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";
import { Badge } from "@/components/ui/badge";

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

  return (
    <div className="flex h-full w-full flex-col items-center justify-center px-4">
      <div className="flex w-full max-w-3xl flex-col items-center text-center pb-28 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex justify-center pb-8">
          <img src="/pricoLogo.png" alt="Prico AI Logo" className="h-16 md:h-20 w-auto object-contain" />
        </div>

        <BotInputArea
          errorMessage={errorMessage}
          inputValue={inputValue}
          isLoading={isResponding}
          onInputValueChange={onInputValueChange}
          onSubmit={onSubmit}
        />

        <Suggestions className="mt-5 max-w-3xl">
          {suggestions.map((suggestion) => (
            <Suggestion
              key={suggestion}
              className="rounded-md text-sm py-1 px-5 h-auto transition-colors"
              onClick={() => onSubmit({ text: suggestion, files: [] })}
              suggestion={suggestion}
            />
          ))}
        </Suggestions>
      </div>
    </div>
  );
}
