import { useEffect, useMemo, useRef, useState } from "react";

import type { TemplateMessage, TemplateTextBlock } from "./types";

type ActiveStreamingMessage = {
  blockIndex: number;
  id: string;
  targetText: string;
};

type StreamingViewOptions = {
  charsPerSecond?: number;
  maxBurstCharsPerFrame?: number;
};

const DEFAULT_OPTIONS: Required<StreamingViewOptions> = {
  charsPerSecond: 72,
  maxBurstCharsPerFrame: 20,
};

function getActiveStreamingMessage(messages: TemplateMessage[]): ActiveStreamingMessage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant") continue;
    if (message.runStatus !== "streaming" && message.runStatus !== "pending") continue;

    const blocks = message.blocks || [];
    let blockIndex = -1;
    for (let blockCursor = blocks.length - 1; blockCursor >= 0; blockCursor -= 1) {
      if (blocks[blockCursor]?.kind === "text") {
        blockIndex = blockCursor;
        break;
      }
    }
    if (blockIndex === -1) {
      return {
        id: message.id,
        blockIndex: -1,
        targetText: "",
      };
    }

    const textBlock = blocks[blockIndex];
    return {
      id: message.id,
      blockIndex,
      targetText: textBlock?.kind === "text" ? textBlock.content : "",
    };
  }

  return null;
}

export function useStreamingMessageView(
  messages: TemplateMessage[],
  options?: StreamingViewOptions,
): TemplateMessage[] {
  const settings = {
    ...DEFAULT_OPTIONS,
    ...options,
  };

  const activeMessage = useMemo(() => getActiveStreamingMessage(messages), [messages]);
  const targetText = activeMessage?.targetText || "";
  const [displayedText, setDisplayedText] = useState(targetText);
  const targetRef = useRef(targetText);
  const displayedRef = useRef(targetText);
  const rafRef = useRef<number | null>(null);
  const lastFrameAtRef = useRef<number | null>(null);

  useEffect(() => {
    targetRef.current = targetText;
  }, [targetText]);

  useEffect(() => {
    if (!activeMessage) {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastFrameAtRef.current = null;
      displayedRef.current = "";
      setDisplayedText("");
      return;
    }

    setDisplayedText((current) => {
      if (activeMessage.targetText.startsWith(current)) {
        displayedRef.current = current;
        return current;
      }
      displayedRef.current = "";
      return "";
    });
  }, [activeMessage?.id, activeMessage]);

  useEffect(() => {
    if (!activeMessage || !targetText) {
      if (!activeMessage) {
        return;
      }
      displayedRef.current = "";
      setDisplayedText("");
      return;
    }

    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
      displayedRef.current = targetText;
      setDisplayedText(targetText);
      return;
    }

    const tick = (timestamp: number) => {
      const previousTimestamp = lastFrameAtRef.current ?? timestamp;
      lastFrameAtRef.current = timestamp;

      const target = targetRef.current;
      const current = displayedRef.current;

      if (current.length >= target.length) {
        rafRef.current = null;
        return;
      }

      const elapsedMs = Math.max(8, timestamp - previousTimestamp);
      const charsFromTime = Math.max(
        1,
        Math.floor((elapsedMs / 1000) * settings.charsPerSecond),
      );
      const gap = target.length - current.length;
      const catchupStep =
        gap > settings.maxBurstCharsPerFrame * 2
          ? Math.min(settings.maxBurstCharsPerFrame, Math.ceil(gap / 10))
          : charsFromTime;
      const nextLength = Math.min(target.length, current.length + Math.max(charsFromTime, catchupStep));
      const next = target.slice(0, nextLength);

      displayedRef.current = next;
      setDisplayedText(next);
      rafRef.current = window.requestAnimationFrame(tick);
    };

    if (rafRef.current === null && displayedRef.current.length < targetText.length) {
      rafRef.current = window.requestAnimationFrame(tick);
    }

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastFrameAtRef.current = null;
    };
  }, [activeMessage, settings.charsPerSecond, settings.maxBurstCharsPerFrame, targetText]);

  return useMemo(() => {
    if (!activeMessage || activeMessage.blockIndex < 0 || displayedText === targetText) {
      return messages;
    }

    return messages.map((message) => {
      if (message.id !== activeMessage.id) {
        return message;
      }

      const nextBlocks = [...(message.blocks || [])];
      const rawBlock = nextBlocks[activeMessage.blockIndex];
      if (!rawBlock || rawBlock.kind !== "text") {
        return message;
      }

      nextBlocks[activeMessage.blockIndex] = {
        ...(rawBlock as TemplateTextBlock),
        content: displayedText,
      };

      return {
        ...message,
        text: displayedText,
        blocks: nextBlocks,
      };
    });
  }, [activeMessage, displayedText, messages, targetText]);
}
