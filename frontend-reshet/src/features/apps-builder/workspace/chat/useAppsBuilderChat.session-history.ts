import type { CodingAgentChatSessionDetail } from "@/services";

import type { TimelineItem } from "./chat-model";
import { buildTimelineFromChatHistory } from "./useAppsBuilderChat.history";
import { prependTimelineWithoutDuplicates } from "./useAppsBuilderChat.session-state";

export function extractHistoryTimeline(detail: CodingAgentChatSessionDetail): TimelineItem[] {
  return buildTimelineFromChatHistory(detail);
}

export function extractHistoryPaging(detail: CodingAgentChatSessionDetail): {
  hasMore: boolean;
  nextBeforeMessageId: string | null;
} {
  return {
    hasMore: Boolean(detail.paging?.has_more),
    nextBeforeMessageId: String(detail.paging?.next_before_message_id || "").trim() || null,
  };
}

export function prependOlderHistoryTimeline(currentTimeline: TimelineItem[], olderTimeline: TimelineItem[]): TimelineItem[] {
  return prependTimelineWithoutDuplicates(currentTimeline, olderTimeline);
}
