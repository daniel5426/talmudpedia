import { act, renderHook, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

import { useArtifactCodingChat } from "@/features/artifact-coding/useArtifactCodingChat";
import { artifactsService } from "@/services/artifacts";

jest.mock("@/services/artifacts", () => ({
  artifactsService: {
    listCodingAgentChatSessions: jest.fn(),
    listCodingAgentModels: jest.fn(),
    submitCodingAgentPrompt: jest.fn(),
    streamCodingAgentRun: jest.fn(),
    getCodingAgentChatSession: jest.fn(),
    cancelCodingAgentRun: jest.fn(),
  },
}));

const mockedArtifactsService = artifactsService as unknown as {
  listCodingAgentChatSessions: jest.Mock;
  listCodingAgentModels: jest.Mock;
  submitCodingAgentPrompt: jest.Mock;
  streamCodingAgentRun: jest.Mock;
  getCodingAgentChatSession: jest.Mock;
  cancelCodingAgentRun: jest.Mock;
};

global.TextDecoder = TextDecoder as typeof global.TextDecoder;
global.TextEncoder = TextEncoder as typeof global.TextEncoder;

function createClosedStreamResponse(): Response {
  const reader = {
    read: jest.fn(async () => ({ done: true, value: undefined })),
    cancel: jest.fn(async () => undefined),
  };
  return {
    ok: true,
    body: {
      getReader: () => reader,
    },
  } as Response;
}

function createStreamingResponse(frames: string[]): Response {
  const encodedFrames = frames.map((frame) => new TextEncoder().encode(frame));
  let index = 0;
  let cancelResolver: (() => void) | null = null;
  const waitForCancel = new Promise<void>((resolve) => {
    cancelResolver = resolve;
  });
  const reader = {
    read: jest.fn(async () => {
      if (index < encodedFrames.length) {
        return { done: false, value: encodedFrames[index++] };
      }
      await waitForCancel;
      return { done: true, value: undefined };
    }),
    cancel: jest.fn(async () => {
      cancelResolver?.();
      return undefined;
    }),
  };
  return {
    ok: true,
    body: {
      getReader: () => reader,
    },
  } as Response;
}

function buildSessionDetail(artifactId?: string | null, draftKey?: string | null) {
  return {
    session: {
      id: "session-1",
      title: "Draft chat",
      artifact_id: artifactId ?? null,
      draft_key: draftKey ?? null,
      active_run_id: null,
      last_run_id: "run-1",
      created_at: "2026-03-25T10:00:00Z",
      updated_at: "2026-03-25T10:00:00Z",
      last_message_at: "2026-03-25T10:00:00Z",
    },
    messages: [],
    run_events: [],
    draft_snapshot: {},
    paging: {
      has_more: false,
      next_before_message_id: null,
    },
  };
}

describe("useArtifactCodingChat scope payloads", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedArtifactsService.listCodingAgentChatSessions.mockResolvedValue([]);
    mockedArtifactsService.listCodingAgentModels.mockResolvedValue([]);
    mockedArtifactsService.streamCodingAgentRun.mockResolvedValue(createClosedStreamResponse());
    mockedArtifactsService.getCodingAgentChatSession.mockResolvedValue(buildSessionDetail());
    mockedArtifactsService.cancelCodingAgentRun.mockResolvedValue({
      run_id: "run-1",
      status: "cancelled",
      chat_session_id: "session-1",
      artifact_id: null,
      draft_key: "draft-create-1",
      created_at: "2026-03-25T10:00:00Z",
    });
  });

  it("sends draft_key for create-mode prompts", async () => {
    mockedArtifactsService.submitCodingAgentPrompt.mockResolvedValue({
      submission_status: "started",
      chat_session_id: "session-1",
      run: {
        run_id: "run-1",
        status: "queued",
        chat_session_id: "session-1",
        artifact_id: null,
        draft_key: "draft-create-1",
        created_at: "2026-03-25T10:00:00Z",
      },
    });
    mockedArtifactsService.getCodingAgentChatSession.mockResolvedValue(buildSessionDetail(null, "draft-create-1"));

    const { result } = renderHook(() =>
      useArtifactCodingChat({
        tenantSlug: "tenant-1",
        tenantId: "tenant-id-1",
        artifactId: null,
        draftKey: "draft-create-1",
        isCreateMode: true,
        getDraftSnapshot: () => ({ display_name: "Draft artifact" }),
        onApplyDraftSnapshot: jest.fn(),
        onError: jest.fn(),
      }),
    );

    await waitFor(() => {
      expect(mockedArtifactsService.listCodingAgentModels).toHaveBeenCalled();
    });

    await act(async () => {
      await result.current.sendMessage("Create the artifact");
    });

    expect(mockedArtifactsService.submitCodingAgentPrompt).toHaveBeenCalledWith(
      expect.objectContaining({
        input: "Create the artifact",
        artifact_id: undefined,
        draft_key: "draft-create-1",
        draft_snapshot: { display_name: "Draft artifact" },
      }),
      "tenant-1",
    );
  });

  it("omits draft_key for saved-artifact prompts", async () => {
    mockedArtifactsService.submitCodingAgentPrompt.mockResolvedValue({
      submission_status: "started",
      chat_session_id: "session-1",
      run: {
        run_id: "run-1",
        status: "queued",
        chat_session_id: "session-1",
        artifact_id: "artifact-1",
        draft_key: null,
        created_at: "2026-03-25T10:00:00Z",
      },
    });
    mockedArtifactsService.getCodingAgentChatSession.mockResolvedValue(buildSessionDetail("artifact-1", null));

    const { result } = renderHook(() =>
      useArtifactCodingChat({
        tenantSlug: "tenant-1",
        tenantId: "tenant-id-1",
        artifactId: "artifact-1",
        draftKey: "draft-create-1",
        isCreateMode: false,
        getDraftSnapshot: () => ({ display_name: "Saved artifact" }),
        onApplyDraftSnapshot: jest.fn(),
        onError: jest.fn(),
      }),
    );

    await waitFor(() => {
      expect(mockedArtifactsService.listCodingAgentModels).toHaveBeenCalled();
    });

    await act(async () => {
      await result.current.sendMessage("Update the artifact");
    });

    expect(mockedArtifactsService.submitCodingAgentPrompt).toHaveBeenCalledWith(
      expect.objectContaining({
        input: "Update the artifact",
        artifact_id: "artifact-1",
        draft_key: undefined,
        draft_snapshot: { display_name: "Saved artifact" },
      }),
      "tenant-1",
    );
  });

  it("sends streamed assistant text when aborting a run", async () => {
    mockedArtifactsService.submitCodingAgentPrompt.mockResolvedValue({
      submission_status: "started",
      chat_session_id: "session-1",
      run: {
        run_id: "run-1",
        status: "queued",
        chat_session_id: "session-1",
        artifact_id: null,
        draft_key: "draft-create-1",
        created_at: "2026-03-25T10:00:00Z",
      },
    });
    mockedArtifactsService.streamCodingAgentRun.mockResolvedValue(
      createStreamingResponse([
        'data: {"event":"assistant.delta","payload":{"content":"partial reply"}}\n\n',
      ]),
    );

    const { result } = renderHook(() =>
      useArtifactCodingChat({
        tenantSlug: "tenant-1",
        tenantId: "tenant-id-1",
        artifactId: null,
        draftKey: "draft-create-1",
        isCreateMode: true,
        getDraftSnapshot: () => ({ display_name: "Draft artifact" }),
        onApplyDraftSnapshot: jest.fn(),
        onError: jest.fn(),
      }),
    );

    await waitFor(() => {
      expect(mockedArtifactsService.listCodingAgentModels).toHaveBeenCalled();
    });

    await act(async () => {
      void result.current.sendMessage("Create the artifact");
    });

    await waitFor(() => {
      expect(result.current.isSending).toBe(true);
      expect(result.current.timeline.some((item) => item.kind === "assistant" && item.description === "partial reply")).toBe(true);
    });

    await act(async () => {
      await result.current.stopCurrentRun();
    });

    expect(mockedArtifactsService.cancelCodingAgentRun).toHaveBeenCalledWith(
      "run-1",
      "tenant-1",
      { assistant_output_text: "partial reply" },
    );
  });
});
