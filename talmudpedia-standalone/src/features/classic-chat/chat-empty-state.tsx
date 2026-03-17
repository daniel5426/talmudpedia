import {
  Suggestion,
  Suggestions,
} from "@/components/ai-elements/suggestion";

import { BotInputArea } from "./bot-input-area";

type ChatEmptyStateProps = {
  errorMessage?: string | null;
  inputValue: string;
  isResponding: boolean;
  onInputValueChange: (value: string) => void;
  onSubmit: (text: string) => void;
  suggestions: string[];
};

export function ChatEmptyState({
  errorMessage,
  inputValue,
  isResponding,
  onInputValueChange,
  onSubmit,
  suggestions,
}: ChatEmptyStateProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center px-4">
      <div className="flex w-full max-w-3xl flex-col items-center text-center pb-28 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <p className="text-3xl font-semibold pb-6 text-foreground">
          Ready when you are.
        </p>

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
              className="rounded-full"
              onClick={onSubmit}
              suggestion={suggestion}
            />
          ))}
        </Suggestions>
      </div>
    </div>
  );
}
