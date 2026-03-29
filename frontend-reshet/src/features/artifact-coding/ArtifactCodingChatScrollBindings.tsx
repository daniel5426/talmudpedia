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
    if (node) {
      node.setAttribute("data-admin-page-scroll", "true");
    }
    onScrollContainerChange(node);
    return () => {
      if (node) {
        node.removeAttribute("data-admin-page-scroll");
      }
      onScrollContainerChange(null);
    };
  }, [onScrollContainerChange, scrollRef]);

  return null;
}
