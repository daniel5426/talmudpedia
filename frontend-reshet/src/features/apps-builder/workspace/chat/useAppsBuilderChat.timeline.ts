import { useCallback, useState } from "react";

import {
  TimelineItem,
  timelineId,
  ToolRunStatus,
  TimelineTone,
  type UserDeliveryStatus,
} from "./chat-model";

export type QueuedPrompt = {
  id: string;
  text: string;
  createdAt: number;
  clientMessageId?: string | null;
  modelId?: string | null;
};

export function useAppsBuilderChatTimelineState() {
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [queuedPrompts, setQueuedPrompts] = useState<QueuedPrompt[]>([]);

  const resetTimelineState = useCallback(() => {
    setTimeline([]);
    setQueuedPrompts([]);
  }, []);

  const pushTimeline = useCallback((item: Omit<TimelineItem, "id" | "kind"> & { kind?: TimelineItem["kind"] }) => {
    setTimeline((prev) => [...prev, { ...item, kind: item.kind || "assistant", id: timelineId("timeline") }]);
  }, []);

  const appendUserTimeline = useCallback(
    ({
      input,
      status,
      clientMessageId,
      queueItemId,
    }: {
      input: string;
      status: UserDeliveryStatus;
      clientMessageId: string;
      queueItemId?: string | null;
    }): string => {
      const id = timelineId("user");
      setTimeline((prev) => [
        ...prev,
        {
          id,
          kind: "user",
          title: "User request",
          description: input,
          tone: "default",
          userDeliveryStatus: status,
          clientMessageId,
          queueItemId: queueItemId || undefined,
        },
      ]);
      return id;
    },
    [],
  );

  const updateUserTimelineDelivery = useCallback(
    ({
      timelineId,
      status,
      queueItemId,
    }: {
      timelineId?: string | null;
      status: UserDeliveryStatus;
      queueItemId?: string | null;
    }) => {
      const resolvedTimelineId = String(timelineId || "").trim();
      if (!resolvedTimelineId) return;
      setTimeline((prev) => {
        const index = prev.findIndex((item) => item.id === resolvedTimelineId && item.kind === "user");
        if (index < 0) return prev;
        const next = [...prev];
        next[index] = {
          ...next[index],
          userDeliveryStatus: status,
          queueItemId: queueItemId || next[index].queueItemId,
        };
        return next;
      });
    },
    [],
  );

  const upsertAssistantTimeline = useCallback((assistantStreamId: string, description: string) => {
    setTimeline((prev) => {
      const existingIndex = prev.findIndex(
        (item) => item.kind === "assistant" && item.assistantStreamId === assistantStreamId,
      );
      if (existingIndex >= 0) {
        const next = [...prev];
        next[existingIndex] = {
          ...next[existingIndex],
          description,
          tone: "default",
        };
        return next;
      }
      return [
        ...prev,
        {
          id: timelineId("assistant"),
          kind: "assistant",
          title: "Assistant",
          description,
          tone: "default",
          assistantStreamId,
        },
      ];
    });
  }, []);

  const upsertToolTimeline = useCallback(
    (
      toolCallId: string,
      title: string,
      status: ToolRunStatus,
      toolName: string,
      toolPath?: string | null,
    ) => {
      setTimeline((prev) => {
        const existingIndex = prev.findIndex(
          (item) => item.kind === "tool" && item.toolCallId === toolCallId,
        );
        const nextTone: TimelineTone | undefined = status === "failed" ? "error" : status === "completed" ? "success" : undefined;
        if (existingIndex >= 0) {
          const next = [...prev];
          next[existingIndex] = {
            ...next[existingIndex],
            title,
            toolStatus: status,
            tone: nextTone,
            toolName,
            toolPath: toolPath || next[existingIndex].toolPath,
          };
          return next;
        }
        return [
          ...prev,
          {
            id: timelineId("tool"),
            kind: "tool",
            toolCallId,
            toolStatus: status,
            title,
            tone: nextTone,
            toolName,
            toolPath: toolPath || undefined,
          },
        ];
      });
    },
    [],
  );

  const finalizeRunningTools = useCallback((status: Extract<ToolRunStatus, "completed" | "failed">) => {
    setTimeline((prev) => {
      let changed = false;
      const tone: TimelineTone = status === "failed" ? "error" : "success";
      const next = prev.map((item) => {
        if (item.kind !== "tool" || item.toolStatus !== "running") return item;
        changed = true;
        return {
          ...item,
          toolStatus: status,
          tone,
        };
      });
      return changed ? next : prev;
    });
  }, []);

  const attachCheckpointToLastUser = useCallback((checkpointId: string) => {
    setTimeline((prev) => {
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].kind === "user" && !prev[i].checkpointId) {
          const next = [...prev];
          next[i] = { ...next[i], checkpointId };
          return next;
        }
      }
      return prev;
    });
  }, []);

  return {
    timeline,
    setTimeline,
    queuedPrompts,
    setQueuedPrompts,
    resetTimelineState,
    pushTimeline,
    appendUserTimeline,
    updateUserTimelineDelivery,
    upsertAssistantTimeline,
    upsertToolTimeline,
    finalizeRunningTools,
    attachCheckpointToLastUser,
  };
}
