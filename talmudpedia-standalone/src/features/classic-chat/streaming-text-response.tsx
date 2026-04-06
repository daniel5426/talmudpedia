import { useEffect, useRef, useState } from "react";

import { MessageResponse } from "@/components/ai-elements/message";

type StreamingTextResponseProps = {
  blockId: string;
  isStreaming: boolean;
  text: string;
};

export function StreamingTextResponse({
  blockId,
  isStreaming,
  text,
}: StreamingTextResponseProps) {
  const [displayedText, setDisplayedText] = useState(isStreaming ? "" : text);
  const targetRef = useRef(text);
  const displayedRef = useRef(displayedText);
  const rafRef = useRef<number | null>(null);
  const lastFrameAtRef = useRef<number | null>(null);
  const blockIdRef = useRef(blockId);
  const shouldAnimateRef = useRef(isStreaming);

  useEffect(() => {
    targetRef.current = text;
  }, [text]);

  useEffect(() => {
    if (blockIdRef.current === blockId) {
      return;
    }
    blockIdRef.current = blockId;
    shouldAnimateRef.current = isStreaming;
    const initial = isStreaming ? "" : text;
    displayedRef.current = initial;
    setDisplayedText(initial);
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    lastFrameAtRef.current = null;
  }, [blockId, isStreaming, text]);

  useEffect(() => {
    if (typeof window === "undefined") {
      displayedRef.current = text;
      setDisplayedText(text);
      return;
    }

    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      displayedRef.current = text;
      setDisplayedText(text);
      shouldAnimateRef.current = false;
      return;
    }

    if (isStreaming) {
      shouldAnimateRef.current = true;
    }

    if (!shouldAnimateRef.current) {
      displayedRef.current = text;
      setDisplayedText(text);
      return;
    }

    if (!text.startsWith(displayedRef.current)) {
      displayedRef.current = "";
      setDisplayedText("");
    }

    const tick = (timestamp: number) => {
      const previousTimestamp = lastFrameAtRef.current ?? timestamp;
      lastFrameAtRef.current = timestamp;

      const target = targetRef.current;
      const current = displayedRef.current;
      if (current.length >= target.length) {
        shouldAnimateRef.current = false;
        rafRef.current = null;
        return;
      }

      const elapsedMs = Math.max(8, timestamp - previousTimestamp);
      const charsFromTime = Math.max(1, Math.floor((elapsedMs / 1000) * 72));
      const gap = target.length - current.length;
      const catchupStep =
        gap > 40 ? Math.min(20, Math.ceil(gap / 10)) : charsFromTime;
      const nextLength = Math.min(
        target.length,
        current.length + Math.max(charsFromTime, catchupStep),
      );
      const next = target.slice(0, nextLength);
      displayedRef.current = next;
      setDisplayedText(next);
      rafRef.current = window.requestAnimationFrame(tick);
    };

    if (rafRef.current === null && displayedRef.current.length < text.length) {
      rafRef.current = window.requestAnimationFrame(tick);
    }

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastFrameAtRef.current = null;
    };
  }, [isStreaming, text]);

  return <MessageResponse>{displayedText}</MessageResponse>;
}
