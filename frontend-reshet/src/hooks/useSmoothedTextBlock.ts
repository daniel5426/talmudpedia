"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type UseSmoothedTextBlockOptions = {
  animateOnMount?: boolean;
  charsPerSecond?: number;
  maxBurstCharsPerFrame?: number;
};

const DEFAULT_OPTIONS: Required<UseSmoothedTextBlockOptions> = {
  animateOnMount: false,
  charsPerSecond: 72,
  maxBurstCharsPerFrame: 20,
};

export function useSmoothedTextBlock(
  blockId: string,
  targetText: string,
  isStreaming: boolean,
  options?: UseSmoothedTextBlockOptions,
) {
  const settings = useMemo(
    () => ({
      ...DEFAULT_OPTIONS,
      ...options,
    }),
    [options],
  );
  const [displayedText, setDisplayedText] = useState(
    settings.animateOnMount || isStreaming ? "" : targetText,
  );
  const targetRef = useRef(targetText);
  const displayedRef = useRef(displayedText);
  const rafRef = useRef<number | null>(null);
  const lastFrameAtRef = useRef<number | null>(null);
  const blockIdRef = useRef(blockId);
  const shouldAnimateRef = useRef(settings.animateOnMount || isStreaming);

  useEffect(() => {
    targetRef.current = targetText;
  }, [targetText]);

  useEffect(() => {
    if (blockIdRef.current === blockId) {
      return;
    }
    blockIdRef.current = blockId;
    shouldAnimateRef.current = settings.animateOnMount || isStreaming;
    const nextInitialText = shouldAnimateRef.current ? "" : targetText;
    displayedRef.current = nextInitialText;
    setDisplayedText(nextInitialText);
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    lastFrameAtRef.current = null;
  }, [blockId, isStreaming, settings.animateOnMount, targetText]);

  useEffect(() => {
    if (typeof window === "undefined") {
      displayedRef.current = targetText;
      setDisplayedText(targetText);
      return;
    }

    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      displayedRef.current = targetText;
      setDisplayedText(targetText);
      shouldAnimateRef.current = false;
      return;
    }

    if (settings.animateOnMount || isStreaming) {
      shouldAnimateRef.current = true;
    }

    if (!shouldAnimateRef.current) {
      displayedRef.current = targetText;
      setDisplayedText(targetText);
      return;
    }

    if (!targetText.startsWith(displayedRef.current)) {
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
      const charsFromTime = Math.max(
        1,
        Math.floor((elapsedMs / 1000) * settings.charsPerSecond),
      );
      const gap = target.length - current.length;
      const catchupStep =
        gap > settings.maxBurstCharsPerFrame * 2
          ? Math.min(settings.maxBurstCharsPerFrame, Math.ceil(gap / 10))
          : charsFromTime;
      const nextLength = Math.min(
        target.length,
        current.length + Math.max(charsFromTime, catchupStep),
      );
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
  }, [
    isStreaming,
    settings.animateOnMount,
    settings.charsPerSecond,
    settings.maxBurstCharsPerFrame,
    targetText,
  ]);

  return displayedText;
}
