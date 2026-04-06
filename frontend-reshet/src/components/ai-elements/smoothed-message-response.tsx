"use client";

import { MessageResponse, type MessageResponseProps } from "./message";
import { useSmoothedTextBlock } from "@/hooks/useSmoothedTextBlock";

type SmoothedMessageResponseProps = Omit<MessageResponseProps, "children"> & {
  animateOnMount?: boolean;
  blockId: string;
  isStreaming?: boolean;
  text: string;
};

export function SmoothedMessageResponse({
  animateOnMount = false,
  blockId,
  isStreaming = false,
  text,
  ...props
}: SmoothedMessageResponseProps) {
  const displayedText = useSmoothedTextBlock(blockId, text, isStreaming, {
    animateOnMount,
  });

  return <MessageResponse {...props}>{displayedText}</MessageResponse>;
}
