import { agentService, type AgentRunEventsResponse } from "@/services/agent";
import type { ChatRenderBlock } from "@/services/chat-presentation";
import {
  adaptRunStreamEvent,
  applyRunStreamEventToBlocks,
  finalizeAssistantRenderBlocks,
  sortChatRenderBlocks,
} from "@/services/chat-presentation";

type FetchRunEvents = (runId: string) => Promise<AgentRunEventsResponse>;

export async function buildResponseBlocksFromRunTrace(
  runId: string,
  assistantText: string,
  fetchRunEvents: FetchRunEvents = agentService.getRunEvents,
): Promise<ChatRenderBlock[] | undefined> {
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) return undefined;

  const response = await fetchRunEvents(normalizedRunId);
  const rawEvents = Array.isArray(response.events) ? response.events : [];
  let blocks: ChatRenderBlock[] = [];
  rawEvents.forEach((event, index) => {
    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(blocks, adaptRunStreamEvent(event, index)),
    );
  });

  const finalized = sortChatRenderBlocks(
    finalizeAssistantRenderBlocks(blocks, assistantText, {
      runId: normalizedRunId,
      fallbackSeq: rawEvents.length + 1,
    }),
  );
  return finalized.length > 0 ? finalized : undefined;
}
