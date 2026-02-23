import { useCallback, useRef, useState } from "react";

import type { CodingAgentPromptQueueItem } from "@/services";

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
};

export function useAppsBuilderChatTimelineState() {
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [queuedPrompts, setQueuedPrompts] = useState<QueuedPrompt[]>([]);

  const queuePromptByIdRef = useRef<Map<string, QueuedPrompt>>(new Map());
  const timelineByClientMessageIdRef = useRef<Map<string, string>>(new Map());
  const queuedTimelineByClientMessageIdRef = useRef<Map<string, string>>(new Map());

  const resetTimelineState = useCallback(() => {
    setTimeline([]);
    setQueuedPrompts([]);
    queuePromptByIdRef.current = new Map();
    timelineByClientMessageIdRef.current = new Map();
    queuedTimelineByClientMessageIdRef.current = new Map();
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
      timelineByClientMessageIdRef.current.set(clientMessageId, id);
      return id;
    },
    [],
  );

  const updateUserTimelineDelivery = useCallback(
    ({
      timelineId,
      clientMessageId,
      status,
      queueItemId,
    }: {
      timelineId?: string | null;
      clientMessageId?: string | null;
      status: UserDeliveryStatus;
      queueItemId?: string | null;
    }) => {
      const resolvedTimelineId =
        String(timelineId || "").trim() ||
        (clientMessageId ? timelineByClientMessageIdRef.current.get(String(clientMessageId)) || "" : "");
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
      const next = prev.map((item) => {
        if (item.kind !== "tool" || item.toolStatus !== "running") return item;
        changed = true;
        return {
          ...item,
          toolStatus: status,
          tone: status === "failed" ? "error" : "success",
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

  const mapQueueItems = useCallback((items: CodingAgentPromptQueueItem[]) => {
    const safeItems = Array.isArray(items) ? items : [];
    const next = [...safeItems]
      .sort((a, b) => {
        const posDiff = Number(a.position || 0) - Number(b.position || 0);
        if (posDiff !== 0) return posDiff;
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      })
      .map((item) => ({
        id: item.id,
        text: String(item.input || "").trim(),
        createdAt: new Date(item.created_at).getTime() || Date.now(),
        clientMessageId: String(item.client_message_id || "").trim() || null,
      }))
      .filter((item) => item.text.length > 0);

    queuePromptByIdRef.current = new Map(next.map((item) => [item.id, item]));
    setQueuedPrompts(next);

    const queuedClientIds = new Set(
      next
        .map((item) => String(item.clientMessageId || "").trim())
        .filter((value) => value.length > 0),
    );

    for (const [clientMessageId, timelineItemId] of queuedTimelineByClientMessageIdRef.current.entries()) {
      const queueMatch = next.find((item) => item.clientMessageId === clientMessageId);
      if (queueMatch) {
        updateUserTimelineDelivery({
          timelineId: timelineItemId,
          status: "queued",
          queueItemId: queueMatch.id,
        });
        continue;
      }
      queuedTimelineByClientMessageIdRef.current.delete(clientMessageId);
      updateUserTimelineDelivery({
        timelineId: timelineItemId,
        status: "sent",
      });
    }

    for (const clientMessageId of queuedClientIds) {
      const timelineItemId = timelineByClientMessageIdRef.current.get(clientMessageId);
      if (!timelineItemId) continue;
      queuedTimelineByClientMessageIdRef.current.set(clientMessageId, timelineItemId);
      const queueMatch = next.find((item) => item.clientMessageId === clientMessageId);
      updateUserTimelineDelivery({
        timelineId: timelineItemId,
        status: "queued",
        queueItemId: queueMatch?.id || null,
      });
    }
  }, [updateUserTimelineDelivery]);

  return {
    timeline,
    setTimeline,
    queuedPrompts,
    setQueuedPrompts,
    queuePromptByIdRef,
    timelineByClientMessageIdRef,
    queuedTimelineByClientMessageIdRef,
    resetTimelineState,
    pushTimeline,
    appendUserTimeline,
    updateUserTimelineDelivery,
    upsertAssistantTimeline,
    upsertToolTimeline,
    finalizeRunningTools,
    attachCheckpointToLastUser,
    mapQueueItems,
  };
}
