from __future__ import annotations

import json


def build_preview_builder_script(*, workspace_path: str) -> str:
    workspace_json = json.dumps(str(workspace_path).rstrip("/"))
    return f"""import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {{ build }} from "vite";

const workspaceRoot = {workspace_json};
const internalRoot = path.join(workspaceRoot, ".talmudpedia", "preview");
const runtimeRoot = path.join(internalRoot, "runtime");
const tempDistRoot = path.join(runtimeRoot, "dist-current");
const buildsRoot = path.join(internalRoot, "builds");
const currentStatePath = path.join(buildsRoot, "current.json");
const latestStatePath = path.join(buildsRoot, "latest-state.json");
const retentionCount = 6;
const ignorePrefixes = [
  ".talmudpedia/",
  ".git/",
  "node_modules/",
  "dist/",
  "build/",
  "coverage/",
  ".vite/",
];

function ensureDir(target) {{
  fs.mkdirSync(target, {{ recursive: true }});
}}

function safeReadJson(target) {{
  try {{
    return JSON.parse(fs.readFileSync(target, "utf8"));
  }} catch {{
    return null;
  }}
}}

function atomicWriteJson(target, payload) {{
  ensureDir(path.dirname(target));
  const temp = `${{target}}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(payload, null, 2), "utf8");
  fs.renameSync(temp, target);
}}

function shouldIgnore(relPath) {{
  if (!relPath) return true;
  return ignorePrefixes.some((prefix) => relPath === prefix.slice(0, -1) || relPath.startsWith(prefix));
}}

function listSourceFiles(root) {{
  const files = [];
  const stack = [root];
  while (stack.length > 0) {{
    const current = stack.pop();
    const entries = fs.readdirSync(current, {{ withFileTypes: true }});
    for (const entry of entries) {{
      const fullPath = path.join(current, entry.name);
      const relPath = path.relative(root, fullPath).split(path.sep).join("/");
      if (shouldIgnore(relPath)) {{
        continue;
      }}
      if (entry.isDirectory()) {{
        stack.push(fullPath);
        continue;
      }}
      if (entry.isFile()) {{
        files.push(relPath);
      }}
    }}
  }}
  files.sort();
  return files;
}}

function copyTree(sourceRoot, targetRoot) {{
  ensureDir(targetRoot);
  for (const relPath of listSourceFiles(sourceRoot)) {{
    const sourcePath = path.join(sourceRoot, relPath);
    const targetPath = path.join(targetRoot, relPath);
    ensureDir(path.dirname(targetPath));
    fs.copyFileSync(sourcePath, targetPath);
  }}
}}

function copyDist(sourceRoot, targetRoot) {{
  ensureDir(targetRoot);
  const stack = [sourceRoot];
  while (stack.length > 0) {{
    const current = stack.pop();
    const entries = fs.readdirSync(current, {{ withFileTypes: true }});
    for (const entry of entries) {{
      const fullPath = path.join(current, entry.name);
      const relPath = path.relative(sourceRoot, fullPath).split(path.sep).join("/");
      if (entry.isDirectory()) {{
        stack.push(fullPath);
        continue;
      }}
      if (!entry.isFile()) {{
        continue;
      }}
      const targetPath = path.join(targetRoot, relPath);
      ensureDir(path.dirname(targetPath));
      fs.copyFileSync(fullPath, targetPath);
    }}
  }}
}}

function buildSourceBundleHash(root) {{
  const hash = crypto.createHash("sha256");
  for (const relPath of listSourceFiles(root)) {{
    hash.update(relPath);
    hash.update("\\0");
    hash.update(fs.readFileSync(path.join(root, relPath)));
    hash.update("\\0");
  }}
  return hash.digest("hex");
}}

function buildDistManifest(distRoot) {{
  const assets = [];
  const stack = [distRoot];
  while (stack.length > 0) {{
    const current = stack.pop();
    const entries = fs.readdirSync(current, {{ withFileTypes: true }});
    for (const entry of entries) {{
      const fullPath = path.join(current, entry.name);
      const relPath = path.relative(distRoot, fullPath).split(path.sep).join("/");
      if (entry.isDirectory()) {{
        stack.push(fullPath);
        continue;
      }}
      if (!entry.isFile()) {{
        continue;
      }}
      assets.push(relPath);
    }}
  }}
  assets.sort();
  return {{
    entry_html: fs.existsSync(path.join(distRoot, "index.html")) ? "index.html" : (assets[0] || "index.html"),
    assets,
  }};
}}

function pruneOldBuilds(currentBuildId) {{
  const entries = fs.existsSync(buildsRoot)
    ? fs.readdirSync(buildsRoot, {{ withFileTypes: true }})
        .filter((entry) => entry.isDirectory() && entry.name !== currentBuildId)
        .sort((left, right) => left.name.localeCompare(right.name))
    : [];
  const removable = entries.slice(0, Math.max(0, entries.length - retentionCount + 1));
  for (const entry of removable) {{
    fs.rmSync(path.join(buildsRoot, entry.name), {{ recursive: true, force: true }});
  }}
}}

let latestKnownState = safeReadJson(latestStatePath) || {{}};
let buildSeq = Number(latestKnownState.build_seq || 0);

function readEntryFile() {{
  const target = path.join(internalRoot, "entry-file.txt");
  try {{
    const value = fs.readFileSync(target, "utf8").trim();
    return value || "src/main.tsx";
  }} catch {{
    return "src/main.tsx";
  }}
}}

function updateLatestState(patch) {{
  latestKnownState = {{
    ...latestKnownState,
    ...patch,
    updated_at: new Date().toISOString(),
  }};
  atomicWriteJson(latestStatePath, latestKnownState);
}}

async function persistSuccessfulBuild() {{
  buildSeq += 1;
  const buildId = `build-${{String(buildSeq).padStart(8, "0")}}`;
  const buildRoot = path.join(buildsRoot, buildId);
  const sourceRoot = path.join(buildRoot, "source");
  const distRoot = path.join(buildRoot, "dist");
  fs.rmSync(buildRoot, {{ recursive: true, force: true }});
  ensureDir(buildRoot);
  copyTree(workspaceRoot, sourceRoot);
  copyDist(tempDistRoot, distRoot);
  const builtAt = new Date().toISOString();
  const state = {{
    build_id: buildId,
    build_seq: buildSeq,
    status: "succeeded",
    built_at: builtAt,
    source_bundle_hash: buildSourceBundleHash(sourceRoot),
    entry_file: readEntryFile(),
    dist_manifest: buildDistManifest(distRoot),
    snapshot_root: buildRoot,
    source_root: sourceRoot,
    dist_root: distRoot,
    last_error: null,
  }};
  atomicWriteJson(path.join(buildRoot, "state.json"), state);
  atomicWriteJson(currentStatePath, {{
    build_id: buildId,
    build_seq: buildSeq,
    built_at: builtAt,
    snapshot_root: buildRoot,
    source_root: sourceRoot,
    dist_root: distRoot,
  }});
  updateLatestState(state);
  pruneOldBuilds(buildId);
}}

function recordFailure(error) {{
  const current = safeReadJson(currentStatePath) || {{}};
  updateLatestState({{
    build_id: current.build_id || null,
    build_seq: Number(current.build_seq || buildSeq || 0),
    built_at: current.built_at || null,
    source_bundle_hash: latestKnownState.source_bundle_hash || null,
    entry_file: latestKnownState.entry_file || "src/main.tsx",
    dist_manifest: latestKnownState.dist_manifest || null,
    snapshot_root: current.snapshot_root || null,
    source_root: current.source_root || null,
    dist_root: current.dist_root || null,
    status: "failed",
    last_error: String(error || "Preview build failed"),
  }});
}}

async function main() {{
  ensureDir(runtimeRoot);
  ensureDir(buildsRoot);
  updateLatestState({{
    status: "building",
    last_error: null,
    entry_file: readEntryFile(),
  }});

  const watcher = await build({{
    root: workspaceRoot,
    logLevel: "info",
    build: {{
      outDir: tempDistRoot,
      emptyOutDir: true,
      watch: {{}},
    }},
  }});

  watcher.on("event", async (event) => {{
    if (event.code === "START") {{
      updateLatestState({{
        status: "building",
        last_error: null,
      }});
      return;
    }}
    if (event.code === "END") {{
      try {{
        await persistSuccessfulBuild();
      }} catch (error) {{
        recordFailure(error && error.message ? error.message : String(error));
      }}
      return;
    }}
    if (event.code === "ERROR") {{
      const message = event.error && event.error.message ? event.error.message : "Preview build failed";
      recordFailure(message);
    }}
  }});
}}

main().catch((error) => {{
  recordFailure(error && error.message ? error.message : String(error));
  console.error(error);
  process.exit(1);
}});
"""


def build_preview_static_server_script(*, workspace_path: str, port: int) -> str:
    workspace_json = json.dumps(str(workspace_path).rstrip("/"))
    port_value = max(1024, int(port))
    return f"""import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const workspaceRoot = {workspace_json};
const buildsRoot = path.join(workspaceRoot, ".talmudpedia", "preview", "builds");
const currentStatePath = path.join(buildsRoot, "current.json");
const latestStatePath = path.join(buildsRoot, "latest-state.json");
const port = {port_value};

function safeReadJson(target) {{
  try {{
    return JSON.parse(fs.readFileSync(target, "utf8"));
  }} catch {{
    return null;
  }}
}}

function contentTypeFor(filePath) {{
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".html") return "text/html; charset=utf-8";
  if (ext === ".js" || ext === ".mjs") return "application/javascript; charset=utf-8";
  if (ext === ".css") return "text/css; charset=utf-8";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".ico") return "image/x-icon";
  return "application/octet-stream";
}}

function resolveCurrentDistRoot() {{
  const current = safeReadJson(currentStatePath);
  if (!current || !current.dist_root) {{
    return null;
  }}
  return String(current.dist_root);
}}

function previewState() {{
  const current = safeReadJson(currentStatePath) || {{}};
  const latest = safeReadJson(latestStatePath) || {{}};
  return {{ ...latest, current }};
}}

const server = http.createServer((request, response) => {{
  const requestUrl = new URL(request.url || "/", `http://${{request.headers.host || "localhost"}}`);
  if (requestUrl.pathname === "/__preview_state") {{
    const payload = previewState();
    response.writeHead(200, {{ "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" }});
    response.end(JSON.stringify(payload));
    return;
  }}

  const distRoot = resolveCurrentDistRoot();
  if (!distRoot) {{
    response.writeHead(503, {{ "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }});
    response.end("Preview build is not ready.");
    return;
  }}

  const requestedPath = decodeURIComponent(requestUrl.pathname || "/");
  let filePath = path.join(distRoot, requestedPath === "/" ? "index.html" : requestedPath.replace(/^\\//, ""));
  if (!filePath.startsWith(distRoot)) {{
    response.writeHead(403, {{ "Content-Type": "text/plain; charset=utf-8" }});
    response.end("Forbidden");
    return;
  }}
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {{
    filePath = path.join(distRoot, "index.html");
  }}
  if (!fs.existsSync(filePath)) {{
    response.writeHead(404, {{ "Content-Type": "text/plain; charset=utf-8" }});
    response.end("Not found");
    return;
  }}
  const headers = {{
    "Content-Type": contentTypeFor(filePath),
    "Cache-Control": filePath.endsWith(".html") ? "no-store" : "public, max-age=31536000, immutable",
  }};
  response.writeHead(200, headers);
  fs.createReadStream(filePath).pipe(response);
}});

server.listen(port, "0.0.0.0", () => {{
  console.log(`preview-static listening on ${{port}}`);
}});
"""
