import { useEffect } from "react";

import { useStickToBottomContext } from "@/components/ai-elements/conversation";

type AppsBuilderChatScrollBindingsProps = {
  onScrollContainerChange: (node: HTMLElement | null) => void;
};

export function AppsBuilderChatScrollBindings({
  onScrollContainerChange,
}: AppsBuilderChatScrollBindingsProps) {
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
