import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { ArtifactCodingPendingQuestion } from "./stream-parsers";

type ArtifactCodingChatQuestionPanelProps = {
  pendingQuestion: ArtifactCodingPendingQuestion;
  isAnsweringQuestion: boolean;
  onAnswerQuestion: (answers: string[][]) => Promise<void>;
};

export function ArtifactCodingChatQuestionPanel({
  pendingQuestion,
  isAnsweringQuestion,
  onAnswerQuestion,
}: ArtifactCodingChatQuestionPanelProps) {
  const [questionStepIndex, setQuestionStepIndex] = useState(0);
  const [questionSelections, setQuestionSelections] = useState<Record<number, string[]>>({});
  const [questionCustomInput, setQuestionCustomInput] = useState<Record<number, string>>({});
  const activeQuestion = useMemo(() => {
    const index = Math.max(0, Math.min(questionStepIndex, pendingQuestion.questions.length - 1));
    return pendingQuestion.questions[index] || null;
  }, [pendingQuestion.questions, questionStepIndex]);
  const canSubmitQuestion = useMemo(
    () => pendingQuestion.questions.some((question, index) => {
      const selections = questionSelections[index] || [];
      const custom = String(questionCustomInput[index] || "").trim();
      return selections.length > 0 || !!custom || question.options.length === 0;
    }),
    [pendingQuestion.questions, questionCustomInput, questionSelections],
  );

  if (!activeQuestion) {
    return null;
  }

  return (
    <section aria-label="Question prompt" className="mb-2 overflow-hidden rounded-lg border border-border/60 bg-background">
      <header className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {activeQuestion.header || "Need your input"}
          </p>
          <p className="mt-0.5 text-xs text-foreground">{activeQuestion.question}</p>
        </div>
        {pendingQuestion.questions.length > 1 ? (
          <span className="text-[11px] text-muted-foreground">{questionStepIndex + 1}/{pendingQuestion.questions.length}</span>
        ) : null}
      </header>
      <div className="space-y-2 p-2.5">
        <div className="grid gap-1.5">
          {activeQuestion.options.map((option) => {
            const selected = (questionSelections[questionStepIndex] || []).includes(option.label);
            return (
              <button
                key={`${pendingQuestion.requestId}-${questionStepIndex}-${option.label}`}
                type="button"
                onClick={() => {
                  const normalizedLabel = String(option.label || "").trim();
                  if (!normalizedLabel) return;
                  setQuestionSelections((prev) => {
                    const current = prev[questionStepIndex] || [];
                    const next = activeQuestion.multiple
                      ? (current.includes(normalizedLabel) ? current.filter((item) => item !== normalizedLabel) : [...current, normalizedLabel])
                      : [normalizedLabel];
                    return { ...prev, [questionStepIndex]: next };
                  });
                }}
                className={cn(
                  "rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                  selected
                    ? "border-foreground/30 bg-muted text-foreground"
                    : "border-border/70 text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
              >
                <div className="font-medium">{option.label}</div>
                {option.description ? <div className="mt-0.5 text-[11px]">{option.description}</div> : null}
              </button>
            );
          })}
        </div>
        <input
          type="text"
          value={questionCustomInput[questionStepIndex] || ""}
          onChange={(event) => setQuestionCustomInput((prev) => ({ ...prev, [questionStepIndex]: event.target.value }))}
          placeholder="Or type your own answer"
          className="h-8 w-full rounded-md border border-border/70 bg-background px-2.5 text-xs outline-none ring-0 placeholder:text-muted-foreground/80 focus:border-foreground/30"
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setQuestionStepIndex((prev) => Math.max(0, prev - 1))} disabled={questionStepIndex <= 0}>Previous</Button>
            <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setQuestionStepIndex((prev) => Math.min(pendingQuestion.questions.length - 1, prev + 1))} disabled={questionStepIndex >= pendingQuestion.questions.length - 1}>Next</Button>
          </div>
          <Button
            type="button"
            size="sm"
            className="h-6 px-2 text-[11px]"
            disabled={isAnsweringQuestion || !canSubmitQuestion}
            onClick={() => {
              const answers = pendingQuestion.questions.map((question, index) => {
                const fromOptions = (questionSelections[index] || []).map((item) => String(item || "").trim()).filter(Boolean);
                const custom = String(questionCustomInput[index] || "").trim();
                if (!custom) return fromOptions;
                return fromOptions.includes(custom) ? fromOptions : [...fromOptions, custom];
              });
              void onAnswerQuestion(answers);
            }}
          >
            {isAnsweringQuestion ? "Submitting..." : "Submit answer"}
          </Button>
        </div>
      </div>
    </section>
  );
}
