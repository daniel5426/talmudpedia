"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowDownIcon } from "lucide-react";
import {
  createContext,
  type ComponentProps,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type ConversationContextValue = {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  isAtBottom: boolean;
  scrollToBottom: () => void;
};

const ConversationContext = createContext<ConversationContextValue | null>(null);

export function useStickToBottomContext() {
  const value = useContext(ConversationContext);
  if (!value) {
    throw new Error("Conversation components must be used inside <Conversation />");
  }
  return value;
}

export type ConversationProps = ComponentProps<"div">;

export const Conversation = ({
  className,
  children,
  ...props
}: ConversationProps) => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  const scrollToBottom = () => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  };

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;

    const handleScroll = () => {
      const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
      setIsAtBottom(distanceFromBottom < 24);
    };

    node.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => node.removeEventListener("scroll", handleScroll);
  }, []);

  const value = useMemo(
    () => ({
      scrollRef,
      isAtBottom,
      scrollToBottom,
    }),
    [isAtBottom],
  );

  return (
    <ConversationContext.Provider value={value}>
      <div
        role="log"
        className={cn("relative flex flex-1 flex-col overflow-hidden", className)}
        {...props}
      >
        {children}
      </div>
    </ConversationContext.Provider>
  );
};

export type ConversationContentProps = ComponentProps<"div">;

export const ConversationContent = ({
  className,
  children,
  scrollClassName,
  ...props
}: ConversationContentProps & { scrollClassName?: string }) => {
  const { isAtBottom, scrollRef, scrollToBottom } = useStickToBottomContext();

  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
    }
  }, [children, isAtBottom]);

  return (
    <div ref={scrollRef} className={cn("min-h-0 flex-1 overflow-y-auto", scrollClassName)}>
      <div className={cn("flex min-h-full flex-col gap-8 p-4", className)} {...props}>
        {children}
      </div>
    </div>
  );
};

export type ConversationScrollButtonProps = ComponentProps<typeof Button>;

export const ConversationScrollButton = ({
  className,
  ...props
}: ConversationScrollButtonProps) => {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) {
    return null;
  }

  return (
    <Button
      className={cn(
        "absolute left-1/2 z-50 -translate-x-1/2 rounded-full shadow-md",
        className,
      )}
      onClick={scrollToBottom}
      size="icon"
      type="button"
      variant="outline"
      {...props}
    >
      <ArrowDownIcon className="size-4" />
    </Button>
  );
};
