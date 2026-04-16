from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict


LIVE_PREVIEW_MODE = "build_watch_static"
LIVE_PREVIEW_STATUS_BOOTING = "booting"
LIVE_PREVIEW_STATUS_BUILDING = "building"
LIVE_PREVIEW_STATUS_READY = "ready"
LIVE_PREVIEW_STATUS_FAILED_KEEP_LAST_GOOD = "failed_keep_last_good"
LIVE_PREVIEW_STATUS_FAILED_NO_BUILD = "failed_no_build"
LIVE_PREVIEW_STATUS_RECOVERING = "recovering"

_VALID_LIVE_PREVIEW_STATUSES = {
    LIVE_PREVIEW_STATUS_BOOTING,
    LIVE_PREVIEW_STATUS_BUILDING,
    LIVE_PREVIEW_STATUS_READY,
    LIVE_PREVIEW_STATUS_FAILED_KEEP_LAST_GOOD,
    LIVE_PREVIEW_STATUS_FAILED_NO_BUILD,
    LIVE_PREVIEW_STATUS_RECOVERING,
}

LIVE_PREVIEW_WATCH_EXCLUDE_GLOBS = (
    ".talmudpedia/**",
    "**/.talmudpedia/**",
    ".opencode/**",
    "**/.opencode/**",
    "node_modules/**",
    "**/node_modules/**",
    ".vite/**",
    "**/.vite/**",
    ".git/**",
    "**/.git/**",
    ".cache/**",
    "**/.cache/**",
    "dist/**",
    "**/dist/**",
    "build/**",
    "**/build/**",
    "coverage/**",
    "**/coverage/**",
)


def build_live_preview_workspace_fingerprint(*, entry_file: str, files: Dict[str, str]) -> str:
    payload = {
        "entry_file": str(entry_file or "").strip() or "src/main.tsx",
        "files": {path: str(files[path]) for path in sorted(files)},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def normalize_live_preview_payload(raw: object) -> dict[str, Any]:
    payload = dict(raw or {}) if isinstance(raw, dict) else {}
    current_build_id = str(payload.get("current_build_id") or "").strip() or None
    last_successful_build_id = str(payload.get("last_successful_build_id") or "").strip() or None
    workspace_fingerprint = str(payload.get("workspace_fingerprint") or "").strip() or None
    dist_path = str(payload.get("dist_path") or "").strip() or None
    error = str(payload.get("error") or "").strip() or None
    raw_status = str(payload.get("status") or "").strip().lower()
    if raw_status == "failed":
        raw_status = (
            LIVE_PREVIEW_STATUS_FAILED_KEEP_LAST_GOOD
            if last_successful_build_id
            else LIVE_PREVIEW_STATUS_FAILED_NO_BUILD
        )
    if raw_status not in _VALID_LIVE_PREVIEW_STATUSES:
        raw_status = LIVE_PREVIEW_STATUS_READY if last_successful_build_id else LIVE_PREVIEW_STATUS_BOOTING
    supervisor_raw = payload.get("supervisor")
    supervisor = dict(supervisor_raw) if isinstance(supervisor_raw, dict) else {}
    return {
        "mode": LIVE_PREVIEW_MODE,
        "status": raw_status,
        "current_build_id": current_build_id,
        "last_successful_build_id": last_successful_build_id,
        "workspace_fingerprint": workspace_fingerprint,
        "dist_path": dist_path,
        "error": error,
        "build_started_at": payload.get("build_started_at"),
        "build_finished_at": payload.get("build_finished_at"),
        "updated_at": payload.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "debug_build_sequence": payload.get("debug_build_sequence"),
        "debug_last_trigger_reason": payload.get("debug_last_trigger_reason"),
        "debug_last_trigger_revision_token": payload.get("debug_last_trigger_revision_token"),
        "debug_last_trigger_workspace_fingerprint": payload.get("debug_last_trigger_workspace_fingerprint"),
        "debug_last_status_transition_at": payload.get("debug_last_status_transition_at"),
        "debug_last_phase": payload.get("debug_last_phase"),
        "debug_last_phase_at": payload.get("debug_last_phase_at"),
        "debug_recent_events": payload.get("debug_recent_events") if isinstance(payload.get("debug_recent_events"), list) else [],
        "supervisor": {
            "build_watch_status": str(supervisor.get("build_watch_status") or "").strip() or None,
            "static_server_status": str(supervisor.get("static_server_status") or "").strip() or None,
            "checked_at": supervisor.get("checked_at"),
            "restart_reason": str(supervisor.get("restart_reason") or "").strip() or None,
            "failure_reason": str(supervisor.get("failure_reason") or "").strip() or None,
        },
    }


def build_live_preview_context_payload(
    *,
    workspace_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "workspace_fingerprint": str(workspace_fingerprint or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_live_preview_watch_script(
    *,
    live_workspace_path: str,
    live_preview_root_path: str,
) -> str:
    return f"""\
import {{ build }} from "vite";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import {{ randomUUID }} from "node:crypto";

const workspacePath = {json.dumps(live_workspace_path)};
const livePreviewRootPath = {json.dumps(live_preview_root_path)};
const buildsRootPath = path.join(livePreviewRootPath, "builds");
const currentLinkPath = path.join(livePreviewRootPath, "current");
const currentTmpLinkPath = path.join(livePreviewRootPath, "current.tmp");
const stagingRootPath = path.join(livePreviewRootPath, "staging");
const stagingDistPath = path.join(stagingRootPath, "dist");
const statusPath = path.join(livePreviewRootPath, "status.json");
const contextPath = path.join(livePreviewRootPath, "context.json");
const revisionTokenPath = path.join(workspacePath, ".talmudpedia", "runtime-revision-token");
const buildRetentionCount = 2;
const watchExclude = {json.dumps(list(LIVE_PREVIEW_WATCH_EXCLUDE_GLOBS))};

fs.mkdirSync(buildsRootPath, {{ recursive: true }});
fs.mkdirSync(stagingRootPath, {{ recursive: true }});

const nowIso = () => new Date().toISOString();
const MAX_DEBUG_EVENTS = 25;

const readJson = (targetPath, fallback) => {{
  try {{
    return JSON.parse(fs.readFileSync(targetPath, "utf8"));
  }} catch {{
    return fallback;
  }}
}};

const readText = (targetPath) => {{
  try {{
    return fs.readFileSync(targetPath, "utf8").trim();
  }} catch {{
    return "";
  }}
}};

const relativizePath = (targetPath) => {{
  const raw = String(targetPath || "").trim();
  if (!raw) {{
    return null;
  }}
  try {{
    const relative = path.relative(workspacePath, raw).replace(/\\\\/g, "/");
    if (!relative || relative.startsWith("../")) {{
      return raw.replace(/\\\\/g, "/");
    }}
    return relative;
  }} catch {{
    return raw.replace(/\\\\/g, "/");
  }}
}};

const writeStatus = (nextStatus) => {{
  const payload = {{
    mode: "build_watch_static",
    status: "booting",
    current_build_id: null,
    last_successful_build_id: null,
    workspace_fingerprint: null,
    dist_path: null,
    error: null,
    build_started_at: null,
    build_finished_at: null,
    debug_build_sequence: 0,
    debug_last_trigger_reason: null,
    debug_last_trigger_revision_token: null,
    debug_last_trigger_workspace_fingerprint: null,
    debug_last_status_transition_at: null,
    debug_last_phase: null,
    debug_last_phase_at: null,
    debug_recent_events: [],
    updated_at: nowIso(),
    ...readJson(statusPath, {{}}),
    ...nextStatus,
    updated_at: nowIso(),
  }};
  fs.writeFileSync(statusPath, JSON.stringify(payload, null, 2));
  return payload;
}};

const pruneBuilds = () => {{
  const entries = fs
    .readdirSync(buildsRootPath, {{ withFileTypes: true }})
    .filter((entry) => entry.isDirectory())
    .map((entry) => {{
      const targetPath = path.join(buildsRootPath, entry.name);
      let mtimeMs = 0;
      try {{
        mtimeMs = fs.statSync(targetPath).mtimeMs;
      }} catch {{}}
      return {{ name: entry.name, targetPath, mtimeMs }};
    }})
    .sort((left, right) => right.mtimeMs - left.mtimeMs);
  for (const entry of entries.slice(buildRetentionCount)) {{
    fs.rmSync(entry.targetPath, {{ recursive: true, force: true }});
  }}
}};

const pushDebugEvent = (event, fields = {{}}) => {{
  const previous = readJson(statusPath, {{}});
  const nextEvent = {{
    at: nowIso(),
    event: String(event || "").trim() || "unknown",
    ...fields,
  }};
  const recentEvents = Array.isArray(previous.debug_recent_events)
    ? previous.debug_recent_events.slice(-(MAX_DEBUG_EVENTS - 1))
    : [];
  writeStatus({{
    debug_last_phase: nextEvent.event,
    debug_last_phase_at: nextEvent.at,
    debug_recent_events: [...recentEvents, nextEvent],
  }});
}};

const promoteDist = (buildId) => {{
  const buildRoot = path.join(buildsRootPath, buildId);
  const buildDistPath = path.join(buildRoot, "dist");
  fs.rmSync(buildRoot, {{ recursive: true, force: true }});
  fs.mkdirSync(buildRoot, {{ recursive: true }});
  fs.cpSync(stagingDistPath, buildDistPath, {{ recursive: true }});
  try {{
    fs.rmSync(currentTmpLinkPath, {{ recursive: true, force: true }});
  }} catch {{}}
  fs.symlinkSync(buildDistPath, currentTmpLinkPath, "dir");
  fs.renameSync(currentTmpLinkPath, currentLinkPath);
  pruneBuilds();
  return buildDistPath;
}};

const readTriggerMetadata = (reason, extra = {{}}) => {{
  const context = readJson(contextPath, {{}});
  return {{
    reason: String(reason || "").trim() || "watch_rebuild",
    revisionToken: readText(revisionTokenPath) || null,
    workspaceFingerprint: String(context.workspace_fingerprint || "").trim() || null,
    ...extra,
  }};
}};

const describeError = (error) => {{
  if (error instanceof Error) {{
    return error.stack || error.message || String(error);
  }}
  return String(error);
}};

let watcher = null;
let shuttingDown = false;
let lastTrigger = readTriggerMetadata("initial_watch_start");
let currentCycle = null;

const beginCycle = () => {{
  const previous = readJson(statusPath, {{}});
  const nextBuildSequence = Number(previous.debug_build_sequence || 0) + 1;
  const trigger = readTriggerMetadata(lastTrigger.reason || "watch_rebuild", {{
    changedPath: lastTrigger.changedPath || null,
    changeEvent: lastTrigger.changeEvent || null,
  }});
  const cycle = {{
    buildId: randomUUID(),
    buildSequence: nextBuildSequence,
    trigger,
    startedAt: nowIso(),
  }};
  currentCycle = cycle;
  fs.rmSync(stagingDistPath, {{ recursive: true, force: true }});
  fs.mkdirSync(stagingRootPath, {{ recursive: true }});
  writeStatus({{
    status: "building",
    current_build_id: cycle.buildId,
    workspace_fingerprint: trigger.workspaceFingerprint,
    error: null,
    build_started_at: cycle.startedAt,
    build_finished_at: null,
    debug_build_sequence: cycle.buildSequence,
    debug_last_trigger_reason: trigger.reason,
    debug_last_trigger_revision_token: trigger.revisionToken,
    debug_last_trigger_workspace_fingerprint: trigger.workspaceFingerprint,
    debug_last_status_transition_at: cycle.startedAt,
    debug_last_phase: "build_begin",
    debug_last_phase_at: cycle.startedAt,
  }});
  pushDebugEvent("build_begin", {{
    build_id: cycle.buildId,
    build_sequence: cycle.buildSequence,
    trigger_reason: trigger.reason,
    revision_token: trigger.revisionToken,
    workspace_fingerprint: trigger.workspaceFingerprint,
    changed_path: trigger.changedPath || null,
    change_event: trigger.changeEvent || null,
  }});
  return cycle;
}};

const failCycle = (cycle, error) => {{
  const previous = readJson(statusPath, {{}});
  const message = describeError(error);
  const buildId = cycle?.buildId || randomUUID();
  const buildSequence = Number(cycle?.buildSequence || previous.debug_build_sequence || 0) || 1;
  const trigger = cycle?.trigger || readTriggerMetadata(lastTrigger.reason || "watch_rebuild");
  writeStatus({{
    status: previous.last_successful_build_id ? "failed_keep_last_good" : "failed_no_build",
    current_build_id: buildId,
    last_successful_build_id: previous.last_successful_build_id || null,
    workspace_fingerprint: trigger.workspaceFingerprint,
    dist_path: previous.dist_path || null,
    error: message,
    build_finished_at: nowIso(),
    debug_build_sequence: buildSequence,
    debug_last_trigger_reason: trigger.reason,
    debug_last_trigger_revision_token: trigger.revisionToken,
    debug_last_trigger_workspace_fingerprint: trigger.workspaceFingerprint,
    debug_last_status_transition_at: nowIso(),
    debug_last_phase: "build_failed",
    debug_last_phase_at: nowIso(),
  }});
  pushDebugEvent("build_failed", {{
    build_id: buildId,
    build_sequence: buildSequence,
    trigger_reason: trigger.reason,
    revision_token: trigger.revisionToken,
    workspace_fingerprint: trigger.workspaceFingerprint,
    changed_path: trigger.changedPath || null,
    change_event: trigger.changeEvent || null,
    error: message,
  }});
  currentCycle = null;
}};

const completeCycle = (cycle) => {{
  if (!cycle) {{
    return;
  }}
  pushDebugEvent("promote_begin", {{
    build_id: cycle.buildId,
    build_sequence: cycle.buildSequence,
  }});
  const distPath = promoteDist(cycle.buildId);
  pushDebugEvent("promote_done", {{
    build_id: cycle.buildId,
    build_sequence: cycle.buildSequence,
    dist_path: distPath,
  }});
  writeStatus({{
    status: "ready",
    current_build_id: cycle.buildId,
    last_successful_build_id: cycle.buildId,
    workspace_fingerprint: cycle.trigger.workspaceFingerprint,
    dist_path: distPath,
    error: null,
    build_finished_at: nowIso(),
    debug_build_sequence: cycle.buildSequence,
    debug_last_trigger_reason: cycle.trigger.reason,
    debug_last_trigger_revision_token: cycle.trigger.revisionToken,
    debug_last_trigger_workspace_fingerprint: cycle.trigger.workspaceFingerprint,
    debug_last_status_transition_at: nowIso(),
    debug_last_phase: "build_ready",
    debug_last_phase_at: nowIso(),
  }});
  pushDebugEvent("build_ready", {{
    build_id: cycle.buildId,
    build_sequence: cycle.buildSequence,
    trigger_reason: cycle.trigger.reason,
    revision_token: cycle.trigger.revisionToken,
    workspace_fingerprint: cycle.trigger.workspaceFingerprint,
    changed_path: cycle.trigger.changedPath || null,
    change_event: cycle.trigger.changeEvent || null,
    dist_path: distPath,
  }});
  currentCycle = null;
}};

writeStatus({{
  status: readJson(statusPath, {{}}).last_successful_build_id ? "ready" : "booting",
  debug_last_status_transition_at: nowIso(),
  debug_last_phase: "script_started",
  debug_last_phase_at: nowIso(),
}});
pushDebugEvent("script_started", {{
  watch_exclude: watchExclude,
}});

const shutdown = async (reason) => {{
  if (shuttingDown) {{
    return;
  }}
  shuttingDown = true;
  pushDebugEvent("watcher_shutdown_begin", {{
    reason: String(reason || "").trim() || "unknown",
  }});
  try {{
    if (watcher && typeof watcher.close === "function") {{
      await watcher.close();
    }}
  }} catch (error) {{
    pushDebugEvent("watcher_shutdown_error", {{
      error: describeError(error),
    }});
  }} finally {{
    pushDebugEvent("watcher_shutdown_done", {{
      reason: String(reason || "").trim() || "unknown",
    }});
  }}
}};

process.on("SIGINT", () => {{
  void shutdown("sigint").finally(() => process.exit(0));
}});
process.on("SIGTERM", () => {{
  void shutdown("sigterm").finally(() => process.exit(0));
}});
process.on("uncaughtException", (error) => {{
  failCycle(currentCycle, error);
  void shutdown("uncaught_exception").finally(() => process.exit(1));
}});
process.on("unhandledRejection", (error) => {{
  failCycle(currentCycle, error);
  void shutdown("unhandled_rejection").finally(() => process.exit(1));
}});

const watcherResult = await build({{
  root: workspacePath,
  logLevel: "info",
  base: "./",
  build: {{
    outDir: stagingDistPath,
    emptyOutDir: true,
    watch: {{
      clearScreen: false,
      exclude: watchExclude,
    }},
  }},
}});

if (!watcherResult || typeof watcherResult.on !== "function") {{
  throw new Error("Vite build watch did not return a watcher instance.");
}}

watcher = watcherResult;
pushDebugEvent("watcher_started", {{
  trigger_reason: lastTrigger.reason,
}});

watcher.on("change", (changedPath, changeInfo) => {{
  lastTrigger = readTriggerMetadata("fs_watch_change", {{
    changedPath: relativizePath(changedPath),
    changeEvent: String(changeInfo?.event || "").trim() || null,
  }});
  pushDebugEvent("watch_change_detected", {{
    trigger_reason: lastTrigger.reason,
    revision_token: lastTrigger.revisionToken,
    workspace_fingerprint: lastTrigger.workspaceFingerprint,
    changed_path: lastTrigger.changedPath || null,
    change_event: lastTrigger.changeEvent || null,
  }});
}});

watcher.on("event", (event) => {{
  const code = String(event?.code || "").trim().toUpperCase();
  if (code === "START") {{
    beginCycle();
    return;
  }}
  if (code === "BUNDLE_START") {{
    if (!currentCycle) {{
      beginCycle();
    }}
    pushDebugEvent("vite_build_begin", {{
      build_id: currentCycle?.buildId || null,
      build_sequence: currentCycle?.buildSequence || null,
      input: Array.isArray(event?.input) ? event.input.map((value) => String(value || "")).slice(0, 12) : event?.input,
      output: Array.isArray(event?.output) ? event.output.map((value) => String(value || "")).slice(0, 12) : event?.output,
    }});
    return;
  }}
  if (code === "BUNDLE_END") {{
    pushDebugEvent("vite_build_done", {{
      build_id: currentCycle?.buildId || null,
      build_sequence: currentCycle?.buildSequence || null,
      duration_ms: Number.isFinite(Number(event?.duration)) ? Number(event.duration) : null,
      output: Array.isArray(event?.output) ? event.output.map((value) => String(value || "")).slice(0, 12) : event?.output,
    }});
    if (event?.result && typeof event.result.close === "function") {{
      void event.result.close().catch(() => undefined);
    }}
    return;
  }}
  if (code === "END") {{
    completeCycle(currentCycle);
    lastTrigger = readTriggerMetadata("watch_rebuild");
    return;
  }}
  if (code === "ERROR") {{
    failCycle(currentCycle, event?.error || new Error("Unknown Vite watch error"));
    return;
  }}
  pushDebugEvent("watch_event", {{
    code: code || null,
  }});
}});

await new Promise(() => {{}});
"""


def build_live_preview_static_server_script(
    *,
    live_preview_root_path: str,
    preview_port: int,
) -> str:
    return f"""\
import json
import mimetypes
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROOT = pathlib.Path({json.dumps(live_preview_root_path)})
CURRENT = ROOT / "current"
STATUS = ROOT / "status.json"
PORT = int({int(preview_port)})


def read_status():
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        return {{
            "mode": "build_watch_static",
            "status": "building",
            "current_build_id": None,
            "last_successful_build_id": None,
            "workspace_fingerprint": None,
            "dist_path": None,
            "error": None,
        }}


class Handler(BaseHTTPRequestHandler):
    server_version = "TalmudpediaLivePreview/1.0"

    def log_message(self, fmt, *args):
        return

    def _send_bytes(self, payload: bytes, *, status: int = 200, content_type: str = "application/octet-stream"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store" if content_type.startswith("text/html") or content_type == "application/json" else "public, max-age=31536000, immutable")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_HEAD(self):
        self._handle()

    def do_GET(self):
        self._handle()

    def _handle(self):
        parsed = urlparse(self.path)
        pathname = unquote(parsed.path or "/")
        if pathname == "/_talmudpedia/status":
            payload = json.dumps(read_status()).encode("utf-8")
            self._send_bytes(payload, content_type="application/json")
            return

        current = CURRENT.resolve(strict=False)
        if not current.exists():
            status_payload = json.dumps(read_status()).encode("utf-8")
            self._send_bytes(status_payload, status=503, content_type="application/json")
            return

        relative = pathname.lstrip("/") or "index.html"
        target = (current / relative).resolve(strict=False)
        is_safe = str(target).startswith(str(current))
        if is_safe and target.exists() and target.is_file():
            self._send_bytes(
                target.read_bytes(),
                content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            )
            return

        fallback = current / "index.html"
        if fallback.exists() and "." not in pathlib.Path(relative).name:
            self._send_bytes(fallback.read_bytes(), content_type="text/html; charset=utf-8")
            return
        self._send_bytes(b"not found", status=404, content_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
"""
