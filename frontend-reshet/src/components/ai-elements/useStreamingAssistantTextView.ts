"use client";

import { useEffect, useRef, useState } from "react";

type StreamingAssistantTextViewOptions = {
  charsPerSecond?: number;
  isStreaming: boolean;
  maxBurstCharsPerFrame?: number;
  streamId: string;
  text: string;
};

const DEFAULT_CHARS_PER_SECOND = 120;
const DEFAULT_MAX_BURST_CHARS_PER_FRAME = 32;

export function useStreamingAssistantTextView({
  charsPerSecond = DEFAULT_CHARS_PER_SECOND,
  isStreaming,
  maxBurstCharsPerFrame = DEFAULT_MAX_BURST_CHARS_PER_FRAME,
  streamId,
  text,
}: StreamingAssistantTextViewOptions): string {
  const [displayedText, setDisplayedText] = useState(text);
  const rafRef = useRef<number | null>(null);
  const lastFrameAtRef = useRef<number | null>(null);
  const displayedRef = useRef(text);
  const targetRef = useRef(text);
  const lastStreamIdRef = useRef(streamId);

  useEffect(() => {
    targetRef.current = text;
  }, [text]);

  useEffect(() => {
    if (lastStreamIdRef.current === streamId) {
      return;
    }
    lastStreamIdRef.current = streamId;
    displayedRef.current = "";
    setDisplayedText("");
    lastFrameAtRef.current = null;
  }, [streamId]);

  useEffect(() => {
    if (!isStreaming) {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      lastFrameAtRef.current = null;
      displayedRef.current = text;
      setDisplayedText(text);
      return;
    }

    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
      displayedRef.current = text;
      setDisplayedText(text);
      return;
    }

    if (!text.startsWith(displayedRef.current)) {
      displayedRef.current = "";
      setDisplayedText("");
      lastFrameAtRef.current = null;
    }

    if (!text) {
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
      const charsFromTime = Math.max(1, Math.floor((elapsedMs / 1000) * charsPerSecond));
      const gap = target.length - current.length;
      const catchupStep =
        gap > maxBurstCharsPerFrame * 2
          ? Math.min(maxBurstCharsPerFrame, Math.ceil(gap / 10))
          : charsFromTime;
      const nextLength = Math.min(
        target.length,
        current.length + Math.max(charsFromTime, catchupStep),
      );
      const nextText = target.slice(0, nextLength);

      displayedRef.current = nextText;
      setDisplayedText(nextText);
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
  }, [charsPerSecond, isStreaming, maxBurstCharsPerFrame, text]);

  return displayedText;
}
