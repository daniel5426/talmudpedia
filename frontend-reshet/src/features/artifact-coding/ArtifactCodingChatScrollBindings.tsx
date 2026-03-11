import { useEffect } from "react";

import { useStickToBottomContext } from "@/components/ai-elements/conversation";

type ArtifactCodingChatScrollBindingsProps = {
  onScrollContainerChange: (node: HTMLElement | null) => void;
};

export function ArtifactCodingChatScrollBindings({
  onScrollContainerChange,
}: ArtifactCodingChatScrollBindingsProps) {
  const { scrollRef } = useStickToBottomContext();

  useEffect(() => {
    const node = scrollRef.current;
    onScrollContainerChange(node);
    return () => {
      onScrollContainerChange(null);
    };
  }, [onScrollContainerChange, scrollRef]);

  return null;
}
