import { useState, useEffect, useRef } from "react";

/**
 * A hook that takes a raw streaming string and returns a "smoothed" version
 * that drips characters at a consistent pace to create a typewriter effect,
 * even when network chunks arrive in large blocks.
 * 
 * @param targetContent The raw content string from the stream
 * @param isStreaming Whether the stream is currently active
 * @param options Configuration for timing and speed
 */
export function useSmoothStream(
  targetContent: string,
  isStreaming: boolean,
  options = {
    baseDelay: 15,    // ms per character
    maxDelay: 30,     // max ms per character
    minDelay: 2,      // min ms per character (for fast catch-up)
    catchupThreshold: 10, // how many chars before we start speeding up
  }
) {
  const [displayedContent, setDisplayedContent] = useState("");
  const targetRef = useRef(targetContent);
  const displayedRef = useRef("");
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Sync refs with props
  useEffect(() => {
    targetRef.current = targetContent;
    
    // If we've finished streaming, we might want to jump to the end 
    // or just let it finish its drip. Usually, jumping to the end 
    // when streaming stops is safer to ensure consistency.
    if (!isStreaming) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setDisplayedContent(targetContent);
      displayedRef.current = targetContent;
    } else {
      // If we are streaming and not already running the loop, start it
      if (!timerRef.current) {
        runLoop();
      }
    }
  }, [targetContent, isStreaming]);

  const runLoop = () => {
    const currentTarget = targetRef.current;
    const currentDisplayed = displayedRef.current;

    if (currentDisplayed.length < currentTarget.length) {
      // Determine how many characters to add this tick
      const gap = currentTarget.length - currentDisplayed.length;
      
      // Calculate delay and step based on gap
      let step = 1;
      let delay = options.baseDelay;

      if (gap > options.catchupThreshold * 5) {
        // Way behind: add more chars per tick
        step = Math.min(gap, Math.ceil(gap / 10));
        delay = options.minDelay;
      } else if (gap > options.catchupThreshold) {
        // Slightly behind: reduce delay or increase step
        step = 1;
        delay = Math.max(options.minDelay, options.baseDelay - 10);
      }

      const nextContent = currentTarget.substring(0, currentDisplayed.length + step);
      displayedRef.current = nextContent;
      setDisplayedContent(nextContent);

      timerRef.current = setTimeout(runLoop, delay);
    } else {
      // We caught up. Reset timer ref so a new update can trigger it again.
      timerRef.current = null;
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return displayedContent;
}
