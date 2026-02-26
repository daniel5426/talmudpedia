# OpenCode Protocol Investigation (Local Probe)

Last Updated: 2026-02-25

## Goal

Investigate OpenCode server protocol behavior directly (without wrapper assumptions), with focus on:
- Interleaved assistant text + tool calls.
- `session.idle` timing.
- Terminal semantics when no explicit `run.completed` event is emitted.

## Probe Setup

Used local `opencode-ai serve` with direct calls to:
- `POST /session`
- `POST /session/{id}/prompt_async`
- `GET /global/event` (SSE)
- `GET /question`
- `POST /question/{id}/reply`
- `GET /session/{id}/message`

Scripts executed:
- `backend/scripts/probe_opencode_question_tool.py`
- `/tmp/opencode_text_tool_text_probe.py`
- `/tmp/opencode_interleaved_question_probe.py`
- `/tmp/opencode_idle_position_probe_short.py`
- `/tmp/opencode_finish_status_probe.py`

Captured JSON artifacts:
- `backend/documentations/summary/opencode_tools_protocol_probe_2026-02-25.json`
  - fresh multi-scenario tools probe (per-scenario session, raw event tails, message snapshots)
- `backend/documentations/summary/opencode_tools_protocol_probe_legacy_2026-02-25.json`
  - earlier tools probe artifact preserved for comparison

## Ground-Truth Findings

1. OpenCode global SSE does not reliably emit `run.completed`.
- In all successful local probe runs, terminal-like closure was represented by:
  - `session.status` transitioning to `{ "type": "idle" }`
  - followed by `session.idle`
- No `run.completed` event was observed in those runs.

2. Assistant work can span multiple assistant messages within one logical run.
- First assistant message can end with:
  - `info.finish = "tool-calls"`
  - `info.time.completed` present
- Then a second assistant message is created and later ends with:
  - `info.finish = "stop"`
  - its own `info.time.completed`

3. `finish = "tool-calls"` is explicitly non-terminal.
- It indicates tool round-trip continuation, not end-of-run.
- Treating this state as terminal causes false mid-run stop.

4. `session.idle` arrived only after final assistant state was `finish = "stop"` in sampled interleaved question flows.
- Across sampled runs, no further progress events appeared after first `session.idle` besides trailing low-signal updates (`message.updated`, `session.diff`).

5. Event shape notes for interleaved text/tool flows:
- `question.asked` and `question.replied` carry stable request correlation.
- Text is streamed primarily via `message.part.delta` (`field: "text"`).
- Tool and reasoning structure appears in `message.part.updated` with part types like:
  - `step-start`, `reasoning`, `tool`, `text`, `step-finish`.

6. Tool event shapes from direct tools probe (`--mode tools`):
- Tool progress appears as repeated `message.part.updated` for one `part.id` with:
  - `part.type = "tool"`, `part.tool`, `part.callID`
  - `part.state.status` transitions (`pending` -> `running` -> `completed`)
- For completed tools, OpenCode populates stable display data in:
  - `part.state.title` (preferred UI label)
  - `part.state.input` (tool args)
  - `part.state.output` (stringified output for grep/read/glob/bash in sampled runs)
  - `part.state.metadata` (includes command exit/truncation for bash)
- `apply_patch` to `/tmp/...` raised `permission.asked` (`external_directory`, pattern `/tmp/*`) and stalled without a reply/auto-approve path.
- `codesearch` may resolve as assistant text-only fallback (`CODESEARCH_UNAVAILABLE`) with no `tool` part emitted.

## Example Evidence (Representative)

From finish-vs-status probe snapshots:
- While active tool cycle:
  - assistant #1: `finish=null` then `finish="tool-calls"`
  - assistant #2 created with `finish=null`
- Later:
  - assistant #2 transitions to `finish="stop"`
  - `session.status: {type: "idle"}` then `session.idle`

This sequence repeated consistently in sampled tool-interleaved runs.

## Practical Protocol Rules (for Wrapper)

1. Do not infer terminal from assistant text completion alone.
2. Do not infer terminal from assistant message with `finish="tool-calls"`.
3. Prefer `session.status=idle` + `session.idle` + settled message state as completion signal when explicit run terminal events are absent.
4. Continue reconciling after transport EOF (`closed_no_terminal`) because OpenCode may have completed despite missing terminal event on stream.
5. For tool row labels, prefer `part.state.title` (and tool input metadata) over parsing arbitrary lines from `part.state.output`; stacktrace/file-reference lines in bash output are not the tool identity.

## Upstream Source Confirmation (sst/opencode)

Cloned upstream reference:
- `.research/sst-opencode`

Findings from source:

1. `session.idle` is compatibility/deprecated, `session.status` is primary.
- File: `.research/sst-opencode/packages/opencode/src/session/status.ts`
- `SessionStatus.set(..., { type: "idle" })` publishes `session.status`.
- It also publishes `session.idle` with a `// deprecated` note.

2. Core loop completion is based on assistant `finish` semantics.
- File: `.research/sst-opencode/packages/opencode/src/session/prompt.ts`
- Loop exits when latest assistant has `finish` and it is not in `["tool-calls", "unknown"]`.
- Explicit check in code: model finished iff finish reason is not `tool-calls`/`unknown`.

3. Official CLI ends wait on `session.status.type === "idle"`.
- File: `.research/sst-opencode/packages/opencode/src/cli/cmd/run.ts`
- The event loop breaks on `session.status` transition to `idle` for that session.

4. UI rendering treats `finish="tool-calls"` as non-final.
- File: `.research/sst-opencode/packages/opencode/src/cli/cmd/tui/routes/session/index.tsx`
- `final` message condition excludes `tool-calls` and `unknown`.

Implication:
- OpenCode’s own clients do not require `run.completed`; they converge on done using session status + message finish semantics.

## Caveats

- Replay durability in wrapper remains in-process; process restart can still produce replay gaps.
- Some prompts are non-deterministic and may not trigger tool calls exactly as requested.
- Local probes used unsecured local OpenCode server (`OPENCODE_SERVER_PASSWORD` not set).
