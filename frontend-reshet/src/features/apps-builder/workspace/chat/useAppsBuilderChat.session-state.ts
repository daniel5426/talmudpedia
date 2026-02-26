import type { CodingAgentPendingQuestion } from "./stream-parsers";
import {
  timelineId,
  type TimelineItem,
  type TimelineTone,
  type ToolRunStatus,
  type UserDeliveryStatus,
} from "./chat-model";

export const DRAFT_SESSION_KEY = "__draft__";
export const LOCAL_SESSION_KEY_PREFIX = "__local__:";
export const DEFAULT_THREAD_TITLE = "New chat";

export function createLocalSessionKey(seed?: string): string {
  const normalizedSeed = String(seed || "").trim();
  if (normalizedSeed) {
    return `${LOCAL_SESSION_KEY_PREFIX}${normalizedSeed}`;
  }
  return `${LOCAL_SESSION_KEY_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function isLocalSessionKey(sessionId: string | null | undefined): boolean {
  const normalized = String(sessionId || "").trim();
  return normalized.startsWith(LOCAL_SESSION_KEY_PREFIX);
}

export function normalizeThreadTitle(rawTitle: string | null | undefined): string {
  const raw = String(rawTitle || "").trim();
  if (!raw) {
    return DEFAULT_THREAD_TITLE;
  }
  const collapsed = raw.split(/\s+/).join(" ").trim();
  if (!collapsed) {
    return DEFAULT_THREAD_TITLE;
  }
  return collapsed.length <= 80 ? collapsed : `${collapsed.slice(0, 77).trimEnd()}...`;
}

export type QueuedPrompt = {
  id: string;
  text: string;
  createdAt: number;
  clientMessageId?: string | null;
  modelId?: string | null;
};

export type SessionHistoryState = {
  initialized: boolean;
  hasMore: boolean;
  nextBeforeMessageId: string | null;
  isLoadingOlder: boolean;
};

export type SessionContainer = {
  key: string;
  timeline: TimelineItem[];
  queuedPrompts: QueuedPrompt[];
  pendingQuestion: CodingAgentPendingQuestion | null;
  isAnsweringQuestion: boolean;
  isSending: boolean;
  isStopping: boolean;
  activeThinkingSummary: string;
  history: SessionHistoryState;
  activeRunIdRef: { current: string | null };
  lastKnownRunIdRef: { current: string | null };
  attachedRunIdRef: { current: string | null };
  attachedRunSessionIdRef: { current: string | null };
  abortReaderRef: { current: ReadableStreamDefaultReader<Uint8Array> | null };
  pendingCancelRef: { current: boolean };
  intentionalAbortRef: { current: boolean };
  isSendingRef: { current: boolean };
  seenRunEventKeysRef: { current: Set<string> };
  streamAttachmentIdRef: { current: number };
  cancelInFlightRunIdRef: { current: string | null };
  isQueueDrainActiveRef: { current: boolean };
};

export function createSessionContainer(key: string): SessionContainer {
  return {
    key,
    timeline: [],
    queuedPrompts: [],
    pendingQuestion: null,
    isAnsweringQuestion: false,
    isSending: false,
    isStopping: false,
    activeThinkingSummary: "",
    history: {
      initialized: false,
      hasMore: false,
      nextBeforeMessageId: null,
      isLoadingOlder: false,
    },
    activeRunIdRef: { current: null },
    lastKnownRunIdRef: { current: null },
    attachedRunIdRef: { current: null },
    attachedRunSessionIdRef: { current: null },
    abortReaderRef: { current: null },
    pendingCancelRef: { current: false },
    intentionalAbortRef: { current: false },
    isSendingRef: { current: false },
    seenRunEventKeysRef: { current: new Set<string>() },
    streamAttachmentIdRef: { current: 0 },
    cancelInFlightRunIdRef: { current: null },
    isQueueDrainActiveRef: { current: false },
  };
}

export function normalizeSessionKey(sessionId: string | null | undefined): string {
  const normalized = String(sessionId || "").trim();
  return normalized || DRAFT_SESSION_KEY;
}

export function createQueuedPrompt(input: string, modelId?: string | null): QueuedPrompt {
  return {
    id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    text: input,
    createdAt: Date.now(),
    clientMessageId: null,
    modelId: modelId || null,
  };
}

export function appendUserTimeline(
  timeline: TimelineItem[],
  {
    input,
    status,
    clientMessageId,
    queueItemId,
  }: {
    input: string;
    status: UserDeliveryStatus;
    clientMessageId: string;
    queueItemId?: string | null;
  },
): { timeline: TimelineItem[]; timelineId: string } {
  const id = timelineId("user");
  return {
    timeline: [
      ...timeline,
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
    ],
    timelineId: id,
  };
}

export function updateUserTimelineDelivery(
  timeline: TimelineItem[],
  {
    timelineId: userTimelineId,
    status,
    queueItemId,
  }: {
    timelineId?: string | null;
    status: UserDeliveryStatus;
    queueItemId?: string | null;
  },
): TimelineItem[] {
  const resolvedTimelineId = String(userTimelineId || "").trim();
  if (!resolvedTimelineId) return timeline;
  const index = timeline.findIndex((item) => item.id === resolvedTimelineId && item.kind === "user");
  if (index < 0) return timeline;
  const next = [...timeline];
  next[index] = {
    ...next[index],
    userDeliveryStatus: status,
    queueItemId: queueItemId || next[index].queueItemId,
  };
  return next;
}

export function upsertAssistantTimeline(timeline: TimelineItem[], assistantStreamId: string, description: string): TimelineItem[] {
  const existingIndex = timeline.findIndex(
    (item) => item.kind === "assistant" && item.assistantStreamId === assistantStreamId,
  );
  if (existingIndex >= 0) {
    const next = [...timeline];
    next[existingIndex] = {
      ...next[existingIndex],
      description,
      tone: "default",
    };
    return next;
  }
  return [
    ...timeline,
    {
      id: timelineId("assistant"),
      kind: "assistant",
      title: "Assistant",
      description,
      tone: "default",
      assistantStreamId,
    },
  ];
}

export function upsertToolTimeline(
  timeline: TimelineItem[],
  toolCallId: string,
  title: string,
  status: ToolRunStatus,
  toolName: string,
  toolPath?: string | null,
  toolDetail?: string | null,
): TimelineItem[] {
  const existingIndex = timeline.findIndex((item) => item.kind === "tool" && item.toolCallId === toolCallId);
  const nextTone: TimelineTone | undefined = status === "failed" ? "error" : status === "completed" ? "success" : undefined;
  if (existingIndex >= 0) {
    const next = [...timeline];
    next[existingIndex] = {
      ...next[existingIndex],
      title,
      toolStatus: status,
      tone: nextTone,
      toolName,
      toolPath: toolPath || next[existingIndex].toolPath,
      toolDetail: toolDetail || next[existingIndex].toolDetail,
    };
    return next;
  }
  return [
    ...timeline,
    {
      id: timelineId("tool"),
      kind: "tool",
      toolCallId,
      toolStatus: status,
      title,
      tone: nextTone,
      toolName,
      toolPath: toolPath || undefined,
      toolDetail: toolDetail || undefined,
    },
  ];
}

export function finalizeRunningTools(timeline: TimelineItem[], status: Extract<ToolRunStatus, "completed" | "failed">): TimelineItem[] {
  let changed = false;
  const tone: TimelineTone = status === "failed" ? "error" : "success";
  const next = timeline.map((item) => {
    if (item.kind !== "tool" || item.toolStatus !== "running") return item;
    changed = true;
    return {
      ...item,
      toolStatus: status,
      tone,
    };
  });
  return changed ? next : timeline;
}

export function attachCheckpointToLastUser(timeline: TimelineItem[], checkpointId: string): TimelineItem[] {
  for (let i = timeline.length - 1; i >= 0; i -= 1) {
    if (timeline[i].kind === "user" && !timeline[i].checkpointId) {
      const next = [...timeline];
      next[i] = { ...next[i], checkpointId };
      return next;
    }
  }
  return timeline;
}

export function prependTimelineWithoutDuplicates(current: TimelineItem[], olderItems: TimelineItem[]): TimelineItem[] {
  if (!olderItems.length) return current;
  const existingIds = new Set(current.map((item) => item.id));
  const itemsToPrepend = olderItems.filter((item) => !existingIds.has(item.id));
  if (!itemsToPrepend.length) return current;
  return [...itemsToPrepend, ...current];
}
