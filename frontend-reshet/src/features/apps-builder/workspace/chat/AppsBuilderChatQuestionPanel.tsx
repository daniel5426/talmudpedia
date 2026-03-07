import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { CodingAgentPendingQuestion } from "./stream-parsers";

type AppsBuilderChatQuestionPanelProps = {
  pendingQuestion: CodingAgentPendingQuestion;
  isAnsweringQuestion: boolean;
  onAnswerQuestion: (answers: string[][]) => Promise<void>;
};

export function AppsBuilderChatQuestionPanel({
  pendingQuestion,
  isAnsweringQuestion,
  onAnswerQuestion,
}: AppsBuilderChatQuestionPanelProps) {
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
      return selections.length > 0 || !!custom;
    }),
    [pendingQuestion.questions, questionCustomInput, questionSelections],
  );

  const handleQuestionOptionToggle = (label: string) => {
    if (!activeQuestion) return;
    const normalizedLabel = String(label || "").trim();
    if (!normalizedLabel) return;
    const questionCount = pendingQuestion.questions.length;
    setQuestionSelections((prev) => {
      const current = prev[questionStepIndex] || [];
      if (activeQuestion.multiple) {
        const next = current.includes(normalizedLabel)
          ? current.filter((item) => item !== normalizedLabel)
          : [...current, normalizedLabel];
        return { ...prev, [questionStepIndex]: next };
      }
      return { ...prev, [questionStepIndex]: [normalizedLabel] };
    });
    if (!activeQuestion.multiple && questionCount > 1 && questionStepIndex < questionCount - 1) {
      setQuestionStepIndex((prev) => Math.min(questionCount - 1, prev + 1));
    }
  };

  const handleSubmitQuestion = async () => {
    const answers = pendingQuestion.questions.map((question, index) => {
      const fromOptions = (questionSelections[index] || []).map((item) => String(item || "").trim()).filter(Boolean);
      const custom = String(questionCustomInput[index] || "").trim();
      if (custom) {
        if (fromOptions.includes(custom)) {
          return fromOptions;
        }
        return [...fromOptions, custom];
      }
      return fromOptions;
    });
    await onAnswerQuestion(answers);
  };

  if (!activeQuestion) {
    return null;
  }

  return (
    <section
      aria-label="Question prompt"
      data-testid="question-prompt-panel"
      className="mb-2 overflow-hidden rounded-lg border border-border/60 bg-background"
    >
      <header className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {activeQuestion.header || "Need your input"}
          </p>
          <p className="mt-0.5 text-xs text-foreground">{activeQuestion.question}</p>
        </div>
        {pendingQuestion.questions.length > 1 ? (
          <span className="text-[11px] text-muted-foreground">
            {questionStepIndex + 1}/{pendingQuestion.questions.length}
          </span>
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
                onClick={() => handleQuestionOptionToggle(option.label)}
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
          onChange={(event) => {
            const value = event.target.value;
            setQuestionCustomInput((prev) => ({ ...prev, [questionStepIndex]: value }));
          }}
          placeholder="Or type your own answer"
          className="h-8 w-full rounded-md border border-border/70 bg-background px-2.5 text-xs outline-none ring-0 placeholder:text-muted-foreground/80 focus:border-foreground/30"
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              onClick={() => setQuestionStepIndex((prev) => Math.max(0, prev - 1))}
              disabled={questionStepIndex <= 0}
            >
              Previous
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              onClick={() =>
                setQuestionStepIndex((prev) => Math.min((pendingQuestion.questions.length || 1) - 1, prev + 1))
              }
              disabled={questionStepIndex >= pendingQuestion.questions.length - 1}
            >
              Next
            </Button>
          </div>
          <Button
            type="button"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={() => {
              void handleSubmitQuestion();
            }}
            disabled={isAnsweringQuestion || !canSubmitQuestion}
          >
            {isAnsweringQuestion ? "Submitting..." : "Submit answer"}
          </Button>
        </div>
      </div>
    </section>
  );
}
