import type { MutableRefObject } from "react";

import { publishedAppsService } from "@/services";

import {
  describeToolIntent,
  extractToolDetailForEvent,
  extractToolPathForEvent,
  extractToolTitleForEvent,
} from "./chat-model";
import {
  type CodingAgentPendingQuestion,
  parsePendingQuestionPayload,
  parseSse,
} from "./stream-parsers";

type ConsumeSessionStreamOptions = {
  appId: string;
  sessionId: string;
  streamAttachmentId?: number;
  getCurrentStreamAttachmentId?: () => number;
  abortReaderRef: MutableRefObject<ReadableStreamDefaultReader<Uint8Array> | null>;
  intentionalAbortRef: MutableRefObject<boolean>;
  isMountedRef: MutableRefObject<boolean>;
  onError: (message: string | null) => void;
  onSetSending: (next: boolean) => void;
  onSetStopping: (next: boolean) => void;
  onSetThinkingSummary: (next: string) => void;
  onConnected?: () => void;
  onUpsertAssistant: (assistantMessageId: string, description: string) => void;
  onUpsertTool: (
    toolCallId: string,
    title: string,
    status: "running" | "completed" | "failed",
    toolName: string,
    toolPath?: string | null,
    toolDetail?: string | null,
  ) => void;
  onFinalizeRunningTools: (status: "completed" | "failed") => void;
  onPermissionUpdated: (question: CodingAgentPendingQuestion) => void;
  onPermissionResolved: (requestId?: string) => void;
  onSessionIdle: () => Promise<void> | void;
};

function findSseFrameBoundary(buffer: string): { index: number; delimiterLength: number } | null {
  const lfBoundary = buffer.indexOf("\n\n");
  const crlfBoundary = buffer.indexOf("\r\n\r\n");
  if (lfBoundary < 0 && crlfBoundary < 0) {
    return null;
  }
  if (lfBoundary < 0) {
    return { index: crlfBoundary, delimiterLength: 4 };
  }
  if (crlfBoundary < 0) {
    return { index: lfBoundary, delimiterLength: 2 };
  }
  return lfBoundary <= crlfBoundary
    ? { index: lfBoundary, delimiterLength: 2 }
    : { index: crlfBoundary, delimiterLength: 4 };
}

function extractMessageId(payload: Record<string, unknown>, part: Record<string, unknown>): string {
  const messageId = String(
    part.messageID
      || part.messageId
      || part.message_id
      || payload.message_id
      || "",
  ).trim();
  if (messageId) {
    return messageId;
  }
  const info = payload.info && typeof payload.info === "object" ? payload.info as Record<string, unknown> : {};
  return String(info.id || "").trim();
}

function extractPartText(payload: Record<string, unknown>, part: Record<string, unknown>): string {
  if (typeof part.text === "string") {
    return part.text;
  }
  if (typeof payload.delta === "string") {
    return payload.delta;
  }
  return "";
}

function summarizeReasoning(text: string): string {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Thinking...";
  }
  return normalized.length <= 120 ? normalized : `${normalized.slice(0, 117).trimEnd()}...`;
}

function normalizeToolStatus(rawStatus: unknown): "running" | "completed" | "failed" {
  const normalized = String(rawStatus || "").trim().toLowerCase();
  if (normalized === "completed" || normalized === "done" || normalized === "success") {
    return "completed";
  }
  if (normalized === "error" || normalized === "failed") {
    return "failed";
  }
  return "running";
}

function extractStreamErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || "Failed to attach coding-agent session stream");
}

function isEventStreamResponse(response: Response): boolean {
  const contentType = String(response.headers.get("content-type") || "").trim().toLowerCase();
  return contentType.includes("text/event-stream");
}

export async function consumeSessionStream(options: ConsumeSessionStreamOptions): Promise<void> {
  const {
    appId,
    sessionId,
    streamAttachmentId,
    getCurrentStreamAttachmentId,
    abortReaderRef,
    intentionalAbortRef,
    isMountedRef,
    onError,
    onSetSending,
    onSetStopping,
    onSetThinkingSummary,
    onConnected,
    onUpsertAssistant,
    onUpsertTool,
    onFinalizeRunningTools,
    onPermissionUpdated,
    onPermissionResolved,
    onSessionIdle,
  } = options;

  const normalizedSessionId = String(sessionId || "").trim();
  if (!normalizedSessionId) {
    return;
  }

  const resolvedAttachmentId = Number.isFinite(Number(streamAttachmentId)) ? Number(streamAttachmentId) : 0;
  const currentAttachmentId = typeof getCurrentStreamAttachmentId === "function"
    ? getCurrentStreamAttachmentId
    : () => resolvedAttachmentId;
  const isCurrentAttachment = (): boolean =>
    isMountedRef.current && currentAttachmentId() === resolvedAttachmentId && !intentionalAbortRef.current;
  let idleSyncInFlight = false;
  const messageRoles = new Map<string, string>();

  const handleIdle = async () => {
    if (idleSyncInFlight) {
      return;
    }
    console.info("[apps-builder][chat-stream]", {
      event: "handleIdle.begin",
      sessionId: normalizedSessionId,
    });
    idleSyncInFlight = true;
    try {
      onPermissionResolved();
      onSetSending(false);
      onSetStopping(false);
      onSetThinkingSummary("");
      onFinalizeRunningTools("completed");
      await onSessionIdle();
    } finally {
      console.info("[apps-builder][chat-stream]", {
        event: "handleIdle.end",
        sessionId: normalizedSessionId,
      });
      idleSyncInFlight = false;
    }
  };

  while (isCurrentAttachment()) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    try {
      const response = await publishedAppsService.streamCodingAgentChatSession(appId, normalizedSessionId);
      console.info("[apps-builder][chat-stream]", {
        event: "attach.response",
        sessionId: normalizedSessionId,
        ok: response.ok,
        status: response.status,
        contentType: response.headers.get("content-type") || "",
      });
      if (!response.ok || !response.body) {
        if (response.status !== 409) {
          onError(`Failed to attach coding-agent session stream (${response.status})`);
        }
        await new Promise((resolve) => setTimeout(resolve, 300));
        continue;
      }
      if (!isEventStreamResponse(response)) {
        throw new Error(
          `Coding-agent session stream returned non-SSE content (${response.headers.get("content-type") || "unknown"})`,
        );
      }

      reader = response.body.getReader();
      abortReaderRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = "";

      while (isCurrentAttachment()) {
        const result = await reader.read();
        console.info("[apps-builder][chat-stream]", {
          event: "attach.read",
          sessionId: normalizedSessionId,
          done: result.done,
          bytes: result.done ? 0 : result.value.byteLength,
        });
        if (result.done) {
          break;
        }
        buffer += decoder.decode(result.value, { stream: true });
        while (true) {
          const boundary = findSseFrameBoundary(buffer);
          if (!boundary) {
            break;
          }
          const frame = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary.delimiterLength);
          const event = parseSse(frame);
          if (!event) {
            continue;
          }
          console.info("[apps-builder][chat-stream]", {
            event: "attach.sse",
            sessionId: normalizedSessionId,
            sseEvent: event.event,
          });
          const payload = event.payload && typeof event.payload === "object"
            ? event.payload as Record<string, unknown>
            : {};
          switch (event.event) {
            case "session.connected":
              onConnected?.();
              break;
            case "session.status": {
              const status = payload.status;
              const statusType = typeof status === "string"
                ? status
                : status && typeof status === "object"
                  ? String((status as Record<string, unknown>).type || "")
                  : "";
              if (statusType.trim().toLowerCase() === "idle") {
                await handleIdle();
              }
              break;
            }
            case "session.idle":
              await handleIdle();
              break;
            case "session.error":
              onSetSending(false);
              onSetStopping(false);
              onSetThinkingSummary("");
              onFinalizeRunningTools("failed");
              if (payload.error) {
                onError(String(payload.error));
              }
              break;
            case "message.updated": {
              const info = payload.info && typeof payload.info === "object"
                ? payload.info as Record<string, unknown>
                : {};
              const messageId = String(info.id || "").trim();
              const role = String(info.role || "").trim().toLowerCase();
              if (messageId && role) {
                messageRoles.set(messageId, role);
              }
              break;
            }
            case "message.part.updated": {
              const part = payload.part && typeof payload.part === "object"
                ? payload.part as Record<string, unknown>
                : null;
              if (!part) {
                break;
              }
              const messageId = extractMessageId(payload, part);
              const messageRole = String(messageRoles.get(messageId) || "").trim().toLowerCase();
              if (messageRole === "user") {
                break;
              }
              const partType = String(part.type || "").trim().toLowerCase();
              if (partType === "reasoning") {
                const reasoningText = extractPartText(payload, part);
                if (reasoningText) {
                  onSetThinkingSummary(summarizeReasoning(reasoningText));
                }
                break;
              }
              if (partType === "text") {
                const nextText = extractPartText(payload, part);
                if (messageId && nextText) {
                  onUpsertAssistant(messageId, nextText);
                }
                break;
              }
              if (partType !== "tool") {
                break;
              }
              const state = part.state && typeof part.state === "object"
                ? part.state as Record<string, unknown>
                : {};
              const toolName = String(part.tool || "tool").trim() || "tool";
              const toolCallId = String(part.callID || part.callId || part.call_id || part.id || "").trim()
                || `${messageId || "tool"}-${toolName}`;
              const toolPayload = {
                tool: toolName,
                span_id: toolCallId,
                input: state.input,
                output: state.output,
                error: state.error,
              };
              const toolStatus = normalizeToolStatus(state.status);
              const toolPath = extractToolPathForEvent(toolName, toolPayload);
              const toolTitle = extractToolTitleForEvent(toolName, toolPayload, toolStatus, toolPath || undefined)
                || String(state.title || "").trim()
                || describeToolIntent(toolName);
              const toolDetail = extractToolDetailForEvent(toolName, toolPayload);
              onUpsertTool(toolCallId, toolTitle, toolStatus, toolName, toolPath || undefined, toolDetail || undefined);
              break;
            }
            case "permission.updated": {
              const question = parsePendingQuestionPayload(payload);
              if (question) {
                onPermissionUpdated(question);
              }
              break;
            }
            case "permission.replied":
              onPermissionResolved(String(payload.request_id || "").trim() || undefined);
              break;
            case "message.part.removed":
              break;
            default:
              break;
          }
        }
      }
    } catch (error) {
      if (isCurrentAttachment()) {
        onError(extractStreamErrorMessage(error));
      }
    } finally {
      if (reader && abortReaderRef.current === reader) {
        abortReaderRef.current = null;
      }
      if (reader) {
        void reader.cancel().catch(() => undefined);
      }
    }
    if (!isCurrentAttachment()) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
}
