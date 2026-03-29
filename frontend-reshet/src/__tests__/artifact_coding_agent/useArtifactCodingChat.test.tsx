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
    getCodingAgentChatSessionDraftSnapshot: jest.fn(),
    cancelCodingAgentRun: jest.fn(),
  },
}));

const mockedArtifactsService = artifactsService as unknown as {
  listCodingAgentChatSessions: jest.Mock;
  listCodingAgentModels: jest.Mock;
  submitCodingAgentPrompt: jest.Mock;
  streamCodingAgentRun: jest.Mock;
  getCodingAgentChatSession: jest.Mock;
  getCodingAgentChatSessionDraftSnapshot: jest.Mock;
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

function createFiniteStreamingResponse(frames: string[]): Response {
  const encodedFrames = frames.map((frame) => new TextEncoder().encode(frame));
  let index = 0;
  const reader = {
    read: jest.fn(async () => {
      if (index < encodedFrames.length) {
        return { done: false, value: encodedFrames[index++] };
      }
      return { done: true, value: undefined };
    }),
    cancel: jest.fn(async () => undefined),
  };
  return {
    ok: true,
    body: {
      getReader: () => reader,
    },
  } as Response;
}

function buildSessionDetail(
  artifactId?: string | null,
  draftKey?: string | null,
  contextWindow?: Record<string, unknown> | null,
) {
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
    context_window: contextWindow ?? null,
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
    mockedArtifactsService.getCodingAgentChatSessionDraftSnapshot.mockResolvedValue({
      session_id: "session-1",
      draft_snapshot: {},
      updated_at: "2026-03-25T10:00:00Z",
    });
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

  it("tracks context status from run submission and stream events", async () => {
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
        context_window: {
          source: "estimated",
          model_id: "openai/gpt-5",
          max_tokens: 1050000,
          max_tokens_source: "provider_fallback",
          input_tokens: 3200,
          remaining_tokens: 1046800,
          usage_ratio: 3200 / 1050000,
        },
      },
    });
    mockedArtifactsService.streamCodingAgentRun.mockResolvedValue(
      createFiniteStreamingResponse([
        'data: {"event":"run.accepted","payload":{"context_window":{"source":"estimated","model_id":"openai/gpt-5","max_tokens":1050000,"max_tokens_source":"provider_fallback","input_tokens":4000,"remaining_tokens":1046000,"usage_ratio":0.0038}}}\n\n',
        'data: {"event":"run.completed","payload":{"context_window":{"source":"exact","model_id":"openai/gpt-5","max_tokens":1050000,"max_tokens_source":"provider_fallback","input_tokens":4100,"remaining_tokens":1045900,"usage_ratio":0.0039},"run_usage":{"source":"exact","input_tokens":4100,"output_tokens":700,"total_tokens":4800}}}\n\n',
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
      await result.current.sendMessage("Create the artifact");
    });

    await waitFor(() => {
      expect(result.current.activeContextStatus?.source).toBe("exact");
      expect(result.current.activeContextStatus?.input_tokens).toBe(4100);
    });
  });

  it("applies live context status events during an active run", async () => {
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
        context_window: {
          source: "estimated",
          model_id: "openai/gpt-5",
          max_tokens: 1050000,
          max_tokens_source: "provider_fallback",
          input_tokens: 3200,
          remaining_tokens: 1046800,
          usage_ratio: 3200 / 1050000,
        },
      },
    });
    mockedArtifactsService.streamCodingAgentRun.mockResolvedValue(
      createFiniteStreamingResponse([
        'data: {"event":"context_window.updated","payload":{"context_window":{"source":"estimated","model_id":"openai/gpt-5","max_tokens":1050000,"max_tokens_source":"provider_fallback","input_tokens":4040,"remaining_tokens":1045960,"usage_ratio":0.0039}}}\n\n',
        'data: {"event":"run.completed","payload":{"status":"completed"}}\n\n',
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
      await result.current.sendMessage("Create the artifact");
    });

    await waitFor(() => {
      expect(result.current.activeContextStatus?.source).toBe("estimated");
      expect(result.current.activeContextStatus?.input_tokens).toBe(4040);
    });
  });

  it("does not regress terminal context status when session reload returns an older snapshot", async () => {
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
        context_window: {
          source: "estimated",
          model_id: "openai/gpt-5",
          max_tokens: 1050000,
          max_tokens_source: "provider_fallback",
          input_tokens: 3200,
          remaining_tokens: 1046800,
          usage_ratio: 3200 / 1050000,
        },
      },
    });
    mockedArtifactsService.streamCodingAgentRun.mockResolvedValue(
      createFiniteStreamingResponse([
        'data: {"event":"run.completed","payload":{"context_window":{"source":"exact","model_id":"openai/gpt-5","max_tokens":1050000,"max_tokens_source":"provider_fallback","input_tokens":4040,"remaining_tokens":1045960,"usage_ratio":0.0039},"run_usage":{"source":"exact","total_tokens":4800}}}\n\n',
      ]),
    );
    mockedArtifactsService.getCodingAgentChatSession.mockResolvedValue(
      buildSessionDetail(
        null,
        "draft-create-1",
        {
          source: "estimated",
          model_id: "openai/gpt-5",
          max_tokens: 1050000,
          max_tokens_source: "provider_fallback",
          input_tokens: 3200,
          remaining_tokens: 1046800,
          usage_ratio: 3200 / 1050000,
        },
      ),
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
      await result.current.sendMessage("Create the artifact");
    });

    await waitFor(() => {
      expect(result.current.activeContextStatus?.source).toBe("exact");
      expect(result.current.activeContextStatus?.input_tokens).toBe(4040);
    });
  });

  it("refreshes the draft snapshot from the dedicated session endpoint when artifact draft updates stream in", async () => {
    const onApplyDraftSnapshot = jest.fn();
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
      createFiniteStreamingResponse([
        'data: {"event":"artifact.draft.updated","payload":{"session_id":"session-1","tool_slug":"artifact-coding-replace-file","changed_fields":["source_files"]}}\n\n',
        'data: {"event":"run.completed","payload":{"status":"completed"}}\n\n',
      ]),
    );
    mockedArtifactsService.getCodingAgentChatSessionDraftSnapshot.mockResolvedValue({
      session_id: "session-1",
      draft_snapshot: { display_name: "Updated draft" },
      updated_at: "2026-03-25T10:01:00Z",
    });

    const { result } = renderHook(() =>
      useArtifactCodingChat({
        tenantSlug: "tenant-1",
        tenantId: "tenant-id-1",
        artifactId: null,
        draftKey: "draft-create-1",
        isCreateMode: true,
        getDraftSnapshot: () => ({ display_name: "Draft artifact" }),
        onApplyDraftSnapshot,
        onError: jest.fn(),
      }),
    );

    await waitFor(() => {
      expect(mockedArtifactsService.listCodingAgentModels).toHaveBeenCalled();
    });

    await act(async () => {
      await result.current.sendMessage("Update the draft");
    });

    await waitFor(() => {
      expect(mockedArtifactsService.getCodingAgentChatSessionDraftSnapshot).toHaveBeenCalledWith("session-1", "tenant-1");
      expect(onApplyDraftSnapshot).toHaveBeenCalledWith({ display_name: "Updated draft" });
    });
  });
});
